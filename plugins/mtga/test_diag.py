"""Diagnostic test for MTGA log line matching."""

with open("docs/log-single-game.log", "r", encoding="utf-8", errors="replace") as f:
    lines = f.readlines()

print(f"Total lines: {len(lines)}")
gre_headers = 0
json_payloads = 0

for i in range(len(lines) - 1):
    curr = lines[i].strip()
    nxt = lines[i+1].strip()
    if "GreToClientEvent" in curr or "GRE_to_Client" in curr or "GreToClient" in curr:
        gre_headers += 1
        if nxt.startswith("{"):
            json_payloads += 1

print(f"GRE Headers found: {gre_headers}")
print(f"Matched JSON payloads found: {json_payloads}")
