import os
import sys
import json
import cv2
import numpy as np
import pytesseract
from dotenv import load_dotenv
from ingestion.collectors.screen_collector import ScreenCollector
from infrastructure.logger import log


load_dotenv(override=True)

CONFIG_FILE = "layout.json"
anchor_flag = False

# Global application states
current_frame: np.ndarray | None = None
original_frame: np.ndarray | None = None
box_to_save: dict | None = None
layouts = {}
selected_box_name = None
awaiting_input = False
input_text = ""
requires_hover_flag = False
# add alongside the other globals near the top
ignore_motion_flag = False
# add alongside the other globals near the top

# Interaction state machine
interaction_mode = "none"
drag_start_x, drag_start_y = -1, -1
initial_box_state = {}


def load_existing_layout():
    global layouts
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            try:
                layouts = json.load(f)
            except json.JSONDecodeError:
                layouts = {}
    else:
        layouts = {}


def save_to_disk():
    os.makedirs(os.path.dirname(CONFIG_FILE) or ".", exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(layouts, f, indent=4)
    log("Layout changes successfully saved to {config_file}", config_file=CONFIG_FILE)


def get_box_handles(x, y, w, h):
    """Returns a dictionary of handle rectangles for a given box."""
    return {
        "tl": (x, y),
        "tr": (x + w, y),
        "bl": (x, y + h),
        "br": (x + w, y + h),
        "t": (x + w // 2, y),
        "b": (x + w // 2, y + h),
        "l": (x, y + h // 2),
        "r": (x + w, y + h // 2),
    }


def redraw_canvas():
    """Redraws all saved layout boxes, handles for the selected box, and pending new box if any."""
    global original_frame, current_frame, layouts, selected_box_name, awaiting_input, box_to_save
    if original_frame is None:
        return
    current_frame = original_frame.copy()

    for name, data in layouts.items():
        x, y, w, h = data["x"], data["y"], data["w"], data["h"]
        requires_hover = data.get("requires_hover", False)

        if name == selected_box_name:
            color = (0, 255, 255)  # Bright yellow for selected box
            thickness = 2
        else:
            if data.get("source") == "scribe_auto":
                color = (0, 165, 255)  # orange (BGR) -- unconfirmed, seeded by Scribe
            elif requires_hover:
                color = (255, 0, 255)
            else:
                color = (0, 255, 0)
            thickness = 1

        cv2.rectangle(current_frame, (x, y), (x + w, y + h), color, thickness)
        cv2.putText(
            current_frame,
            name,
            (x, y - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
            cv2.LINE_AA,
        )

        # Draw handles if this box is selected
        if name == selected_box_name:
            handles = get_box_handles(x, y, w, h)
            for h_name, (hx, hy) in handles.items():
                cv2.rectangle(current_frame, (hx - 4, hy - 4), (hx + 4, hy + 4), (255, 255, 255), -1)
                cv2.rectangle(current_frame, (hx - 4, hy - 4), (hx + 4, hy + 4), (0, 0, 0), 1)

    if awaiting_input and box_to_save:
        bx, by, bw, bh = box_to_save["x"], box_to_save["y"], box_to_save["w"], box_to_save["h"]
        p_color = (255, 0, 255) if box_to_save.get("requires_hover") else (0, 255, 0)
        cv2.rectangle(current_frame, (bx, by), (bx + bw, by + bh), p_color, 2)
        cv2.putText(
            current_frame,
            "[NEW BOX]",
            (bx, by - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            p_color,
            1,
            cv2.LINE_AA,
        )


def process_and_ocr_crop(crop, w, h):
    """Dynamic PSM selection based on box proportions for the inspector tool."""
    if crop is None or crop.size == 0:
        return None, ""
    
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    scaled = cv2.resize(gray, (0, 0), fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    _, thresh = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # Determine optimal PSM based on dimensions
    aspect_ratio = w / float(h) if h > 0 else 7
    psm = 7 if aspect_ratio > 3.0 else 6

    try:
        text = pytesseract.image_to_string(thresh, config=f"--psm {psm}").strip()
    except Exception:
        text = "[OCR Error]"
    return thresh, text


def show_ocr_preview(x1, y1, w, h):
    """Triggers the OCR preview window for a given crop region."""
    global original_frame
    if original_frame is None:
        return
    crop = original_frame[y1 : y1 + h, x1 : x1 + w]
    preview_img, detected_text = process_and_ocr_crop(crop, w, h)

    if preview_img is not None:
        preview_bgr = cv2.cvtColor(preview_img, cv2.COLOR_GRAY2BGR)
        ph, pw, _ = preview_bgr.shape
        combined_canvas = np.zeros((ph + 100, max(pw, 400), 3), dtype=np.uint8)
        combined_canvas[:ph, :pw] = preview_bgr
        cv2.rectangle(combined_canvas, (0, ph), (combined_canvas.shape[1], ph + 50), (30, 30, 30), -1)
        cv2.putText(combined_canvas, f"OCR: '{detected_text}'", (10, ph + 32), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA)
        cv2.imshow("Neow's Eye - OCR Result Preview", combined_canvas)
        log(f"OCR: '{detected_text}'")


def mouse_callback(event, x, y, flags, param):
    global current_frame, original_frame, box_to_save, awaiting_input, input_text
    global requires_hover_flag, selected_box_name, layouts, interaction_mode, drag_start_x, drag_start_y, initial_box_state, anchor_flag

    if awaiting_input:
        return

    if event == cv2.EVENT_RBUTTONDOWN:
        if interaction_mode != "none":
            interaction_mode = "none"
            redraw_canvas()
            log("Action canceled.")
        elif selected_box_name:
            selected_box_name = None
            redraw_canvas()
            log("Box deselected.")
        return

    if event == cv2.EVENT_LBUTTONDOWN:
        drag_start_x, drag_start_y = x, y

        # 1. Check handles of selected box
        if selected_box_name and selected_box_name in layouts:
            b = layouts[selected_box_name]
            initial_box_state = b.copy()
            handles = get_box_handles(b["x"], b["y"], b["w"], b["h"])

            hit_handle = None
            for h_name, (hx, hy) in handles.items():
                if abs(x - hx) <= 6 and abs(y - hy) <= 6:
                    hit_handle = h_name
                    break

            if hit_handle:
                interaction_mode = f"resizing_{hit_handle}"
                return

            # 2. Check box body for repositioning
            if b["x"] <= x <= b["x"] + b["w"] and b["y"] <= y <= b["y"] + b["h"]:
                interaction_mode = "repositioning"
                return

        # 3. Check selecting an existing box
        clicked_box = None
        for name, data in layouts.items():
            if data["x"] <= x <= data["x"] + data["w"] and data["y"] <= y <= data["y"] + data["h"]:
                clicked_box = name
                break

        if clicked_box:
            selected_box_name = clicked_box
            interaction_mode = "none"
            redraw_canvas()
            log(f"Selected box: '{selected_box_name}'")
        else:
            # 4. Create new box
            selected_box_name = None
            interaction_mode = "creating"
            redraw_canvas()

    elif event == cv2.EVENT_MOUSEMOVE:
        if interaction_mode == "creating":
            redraw_canvas()
            if current_frame is not None:
                cv2.rectangle(current_frame, (drag_start_x, drag_start_y), (x, y), (0, 255, 0), 2)

        elif interaction_mode == "repositioning" and selected_box_name in layouts:
            dx = x - drag_start_x
            dy = y - drag_start_y
            ib = initial_box_state
            layouts[selected_box_name]["x"] = ib["x"] + dx
            layouts[selected_box_name]["y"] = ib["y"] + dy
            redraw_canvas()

        elif interaction_mode.startswith("resizing_") and selected_box_name in layouts:
            handle = interaction_mode.split("_")[1]
            ib = initial_box_state
            ix, iy, iw, ih = ib["x"], ib["y"], ib["w"], ib["h"]
            dx = x - drag_start_x
            dy = y - drag_start_y

            nx, ny, nw, nh = ix, iy, iw, ih

            if "l" in handle:
                nx = min(ix + dx, ix + iw - 5)
                nw = iw - (nx - ix)
            if "r" in handle:
                nw = max(5, iw + dx)
            if "t" in handle:
                ny = min(iy + dy, iy + ih - 5)
                nh = ih - (ny - iy)
            if "b" in handle:
                nh = max(5, ih + dy)

            layouts[selected_box_name].update({"x": nx, "y": ny, "w": nw, "h": nh})
            redraw_canvas()

    elif event == cv2.EVENT_LBUTTONUP:
        if interaction_mode == "creating":
            x1, y1 = min(drag_start_x, x), min(drag_start_y, y)
            w, h = abs(x - drag_start_x), abs(y - drag_start_y)
            interaction_mode = "none"

            if w < 5 or h < 5:
                redraw_canvas()
                return

            # box creation, in mouse_callback's LBUTTONUP "creating" branch:
            box_to_save = {
                "x": x1, "y": y1, "w": w, "h": h,
                "requires_hover": requires_hover_flag,
                "ignore_motion": ignore_motion_flag,
                "is_anchor": anchor_flag,
            }
            if anchor_flag:
                import base64, io
                frame_ref = original_frame
                if frame_ref is not None:
                    crop = frame_ref[y1:y1 + h, x1:x1 + w]
                    _, buf = cv2.imencode(".png", crop)
                    box_to_save["anchor_reference"] = base64.b64encode(buf).decode()
            awaiting_input = True
            input_text = ""
            
            show_ocr_preview(x1, y1, w, h)
            redraw_canvas()

        elif interaction_mode in ["repositioning"] or interaction_mode.startswith("resizing_"):
            interaction_mode = "none"
            if selected_box_name and selected_box_name in layouts:
                layouts[selected_box_name].pop("source", None)  # human-adjusted -> confirmed
            save_to_disk()
            
            if selected_box_name and selected_box_name in layouts:
                b = layouts[selected_box_name]
                show_ocr_preview(b["x"], b["y"], b["w"], b["h"])

            redraw_canvas()
            log(f"Updated box '{selected_box_name}' dimensions/position.")


def draw_ui_overlay(frame):
    global awaiting_input, input_text, box_to_save, requires_hover_flag, selected_box_name
    h, w, _ = frame.shape

    status_text = (
        f"Hover [H]: {'ON' if requires_hover_flag else 'OFF'} | "
        f"IgnoreMotion [M]: {'ON' if ignore_motion_flag else 'OFF'} | "
        f"Anchor [A]: {'ON' if anchor_flag else 'OFF'} | "
        f"Selected: {selected_box_name or 'None'}"
        f"Selected: {selected_box_name or 'None'}"
    )
    
    text_size = cv2.getTextSize(status_text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)[0]
    hud_x = (w - text_size[0]) // 2
    hud_y = 70

    cv2.rectangle(frame, (hud_x - 10, hud_y - 22), (hud_x + text_size[0] + 10, hud_y + 8), (30, 30, 30), -1)
    cv2.putText(frame, status_text, (hud_x, hud_y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)

    if not awaiting_input or box_to_save is None:
        return frame

    overlay = frame.copy()
    cv2.rectangle(overlay, (0, h - 90), (w, h), (30, 30, 30), -1)
    cv2.addWeighted(overlay, 0.8, frame, 0.2, 0, frame)

    prompt_str = f"Name for new box (ENTER to save): {input_text}_"
    cv2.putText(frame, prompt_str, (20, h - 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA)
    sub_str = f"Size: {box_to_save['w']}x{box_to_save['h']} | ESC to cancel"
    cv2.putText(frame, sub_str, (20, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)
    return frame

def seed_from_scribe():
    """Run the Scribe once against the current frame and stage its
    detected elements as draft layout boxes (source: 'scribe_auto').
    Existing boxes are never overwritten -- a name collision is skipped
    silently, on the assumption the existing box was already confirmed.
    """
    global layouts, original_frame
    if original_frame is None:
        return

    from PIL import Image
    import cv2
    from infrastructure.llm.gemini_provider import GeminiProvider
    from brain.perception.scribe import Scribe
    from brain.perception.geometry import normalized_box_to_pixels

    log("Calling Scribe to seed draft boxes...")
    scribe = Scribe(GeminiProvider())
    h, w = original_frame.shape[:2]
    pil_image = Image.fromarray(cv2.cvtColor(original_frame, cv2.COLOR_BGR2RGB))
    result = scribe.extract(pil_image)

    added = 0
    for el in result.screen_elements:
        name = el.label.strip().lower().replace(" ", "_")
        if name in layouts:
            continue
        x, y, bw, bh = normalized_box_to_pixels(el.box_2d, w, h)
        layouts[name] = {
            "x": x, "y": y, "w": bw, "h": bh,
            "requires_hover": False,
            "ignore_motion": False,
            "psm": 7,
            "source": "scribe_auto",  # unconfirmed -- nudge/rename before trusting for OCR
        }
        added += 1

    save_to_disk()
    log(f"Added {added} draft box(es) from Scribe. Review before trusting for OCR.")


def main():
    global current_frame, original_frame, awaiting_input, input_text, box_to_save, requires_hover_flag, selected_box_name, layouts, anchor_flag, ignore_motion_flag, CONFIG_FILE

    window_title = sys.argv[1] if len(sys.argv) > 1 else "Slay the Spire"
    if len(sys.argv) > 2:
        CONFIG_FILE = sys.argv[2]

    client = ScreenCollector(window_title)
    client.prepare_window()
    original_frame = client.capture_bgr()

    if original_frame is not None:
        load_existing_layout()
        redraw_canvas()

        window_name = "Neow's Eye - Advanced Layout Editor"
        cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(window_name, mouse_callback)

        log("Layout Editor Active.")
        while True:
            if current_frame is None:
                log("Lost the captured frame -- stopping.")
                break

            display_frame = draw_ui_overlay(current_frame.copy())
            cv2.imshow(window_name, display_frame)

            key = cv2.waitKey(1) & 0xFF

            if awaiting_input:
                if key == 13:  # ENTER
                    if input_text.strip():
                        new_name = input_text.strip().lower()
                        layouts[new_name] = box_to_save
                        save_to_disk()
                        selected_box_name = new_name
                    awaiting_input = False
                    input_text = ""
                    box_to_save = None
                    redraw_canvas()
                    try:
                        cv2.destroyWindow("Neow's Eye - OCR Result Preview")
                    except:
                        pass
                elif key == 27:  # ESC cancels prompt
                    awaiting_input = False
                    input_text = ""
                    box_to_save = None
                    redraw_canvas()
                    try:
                        cv2.destroyWindow("Neow's Eye - OCR Result Preview")
                    except:
                        pass
                elif key == 8:  # BACKSPACE
                    input_text = input_text[:-1]
                elif 32 <= key <= 126:
                    input_text += chr(key)
            else:
                if key == ord("q"):
                    break
                elif key == 8 or key == 127:  # BACKSPACE / DELETE
                    if selected_box_name and selected_box_name in layouts:
                        del layouts[selected_box_name]
                        save_to_disk()
                        log(f"Deleted box: '{selected_box_name}'")
                        selected_box_name = None
                        redraw_canvas()
                elif key == ord("h"):
                    requires_hover_flag = not requires_hover_flag
                    log(f"Requires_hover set to: {requires_hover_flag}")
                elif key == ord("m"):
                    ignore_motion_flag = not ignore_motion_flag
                    log(f"Ignore_motion set to: {ignore_motion_flag}")
                elif key == ord("r"):
                    original_frame = client.capture_bgr()
                    redraw_canvas()
                    log("View refreshed.")
                elif key == ord("s"):
                    seed_from_scribe()
                    redraw_canvas()
                elif key == ord("a"):
                    anchor_flag = not anchor_flag
                    log(f"Anchor set to: {anchor_flag}")

        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()