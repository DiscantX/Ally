# "Ally" Project Scope

## Purpose

The purpose of this project is to develop an AI tool that will "play games" with the player. Its name will be "Ally". It will serve as a coach, someone who provides suggestions, and as a companion/co-op player. It will have personality, and feel like someone who is sitting next to you on the couch, and is just as involved in playing the game as the player. The player (or the player and Ally, as a team) will pick games to play together.

## A friend that remembers

Ally isn't just an AI assistant, it's a friend playing games with you. Previous game moments, and interactions with the player, should have a long lasting impact on the personality of Ally. Ally's interactions should reflect not only what is happening in the game at the moment, but also the personality and relationship with the player that has developed over time.

## Scope

The scope of the project needs to be broad -- the code needs to be generalized as much as possible -- it can't narrow anything down to one game format, except for perhaps later down the pipeline (such as through a plugin system that deals with one specific game type or game).

### Generalizability

Development should prefer a "plug and play" approach, rather than writing code around specific games or even genres. To the max extent possible, the program should be built around the concept of the player being able to say "Hey Ally, there's this new game I want to play, let's try it." And Ally is fed the game state information and it provides its feedback.

That said, specialized code or plugins for at least specific genres if not games may be required.

## Tech stack

Development will be in Python, possibly with a frontend web stack if that is what is used for the GUI. Gemini's `genai` python package will be used to access their models. During development, Gemini's `gemini-3.5-flash-lite` model will primarily be the one used, due to the generous (500) RPM limit; however, it should be built so that any model and any provider can be dropped in easily.

### Architectual quesstions

Of consideration are the broader architectual questions of how information will flow through the program, and how it will be organized.

#### Broader design decisions

This project will rely heavily on AI during development. As such considerations such as token usage should be considered. That is — when passing off the project to an AI, it may be necessary to pass off only necessary portions — as such, and for other reasons, this project should be modular. Files should not grow too large. Code should be shared and properly scoped everywhere possible.

An object-oriented, modular approach is the gold standard. A plugin-type system may be desired, such that specific use cases can be developed for. An internal API may be desirable. This all needs to be confirmed in future planning.

#### Flow of information

##### Collection of game data

Information needs to be received from the game to pass onto Ally. This may come from various sources:

1. **Collection of information from the screen:**

    Collection itself should be straightforward; take a screenshot, store it in memory, pass off to the next part of the pipeline.

    * **Processing** will be a major pipeline (OCR, OpenCV, PyTorch, PIL, etc). We may also use modern AI apis to hand off images for processing.

2. **Internal APIs**:

    Occasionally some games may have an internal api or similar in which we can directly receive game state information. One place this was encountered in a different project was through a *Slay the Spire* mod (`CommunicationMod`) that provided exact GameState information. Avenues such as this should be looked at before considering more complex methods.

3. **Memory Scraping:**

    System memory itself could be read directly, though this might require pretty heavy reverse engineering of particular games. It should be avoided where possible.

4. **The Player**

    The player must also be able to feed information to the player. This should be a supplementary way of passing information.

5. **Other:**

    Whether other avenues exist that are not covered here should be considered.

##### Iterface with the AI

The game data will need to be fed to the AI model. This will require a system that can connect to an AI model (ie. through Gemini's `genai` python module), pass it prompts, and receive replies. This should not be specific to any particular AI or model.

## Knowledge & Memory

### (Prior) Knowledge

The AI is almost certain to have been trained on data about a particular game, especially if it is a popular one. This means it may already have an entire walkthrough of the game or similar data in its model. We do not want the AI to utilize this data; Ally should enter into every game as a brand new player learning it for the first time.

#### Mitigation of hidden memorization

One of the fundamental challenge in AI is evaluating **true reasoning** vs. **hidden memorization**. If an AI has prior knowledge of something, and it has been instructed to disregard this prior knowledge, how can we be sure that it is truly not acting on that knowledge?

The need for mitigation strategies will be evaluated through playtesting.

*Note: Focus will at first be on Prompting. We should develop early on a way to leave room for other implementations. A simple hook or method for a processing step may be all that is required.*

##### Mitigation 1: Prompting

This is the most direct and nieve way of handling the issue: Simply tell the AI to disgregard prior knowledge. This has the *appearance* of working as intended. The issue is: *How do we know for sure it is?*

Early development should focus on this approach. Playtesting will reveal if other approaches are required.



##### Mitigation 2: The Multi-Agent "Air-Gap" Solution

Instead of letting one model look at the screen and decide what to do, you split the bot into three isolated scripts:

```Flowchart
[Screen Capture] ──> [Agent A: The Scribe] (Extracts raw visual data only)
                           │
                           ▼
                    [State Sandbox] (Pure text fact-sheet)
                           │
                           ▼
                     [Agent B: The Player] (Makes choices *only* from sandbox)
```

###### Agent A: The Scribe (Sight & Text Extraction)

This agent looks at the game screenshot via **Gemini 3.5 Flash-Lite**. Its only job is to look at the screen and list what is currently happening.

* **The Prompt:** "Extract the exact dialogue option text, the active skill check name, and any highlighted environmental text on screen. Do not interpret what it means, do not name characters unless explicitly written on screen, and do not suggest actions."
* **The Output:** A raw, emotionless JSON file of the current text box and active choices.

###### The State Sandbox (The Memory Vault)

A standard Python script acting as a strict local database. It compiles a running record of facts the Scribe has confirmed during this specific run (e.g., `Current Location: Neon_District_Hotel`, `Active Task: Find missing gadget`, `Inventory: 10 Credits`). It contains zero outside context.

###### Agent B: The Player (The Blind Brain)

This is a separate, text-only LLM instance. You do not give it the screenshot. You only feed it the raw text from the State Sandbox and the current dialogue choices. You explicitly prompt it to roleplay an amnesiac investigator who only knows what is written in the sandbox.

##### Mitigation 3: Anonymizing the Game Data

*Note: An adventure game is used as an example, but the same principles apply to other genres.*

Many adventure games are highly stylized and use distinct keywords. When a model sees specific localized words, it instantly activates its pre-trained memory banks of that game's plot.

To completely break its train of thought, use a Python middleware script to hash or rename the game elements before Agent B reads them:

| Original Game Data | Obfuscated Text Sent to Agent B |
| :--- | :--- |
| Lieutenant Vance | Partner_Alpha |
| Neural Insight (Skill) | Intuition_Attribute_04 |
| The Neon Lounge | Location_Hotel_Main |
| Investigator Alex | Subject_A |

Because Agent B only sees *"Partner_Alpha suggests checking Location_Hotel_Main,"* it is mechanically impossible for the model to cross-reference an online walkthrough. It is forced to solve the game purely using logic and the data sitting inside your Python state machine.



##### Mitigation 4: Masking Visual Cues (For Agent A)

If Agent A sees the iconic, recognizable art style of a popular title, it might still deduce the game identity. If you want to be completely rigorous:

* Use a local library like **OpenCV** to apply color-thresholding filters or convert screenshots to high-contrast black-and-white lines.
* Crop the image strictly to the dialogue box region on the screen.

This turns the multimodal task into a clean, text-heavy layout extraction job, blinding the model to the game's recognizable aesthetic.

---

### Memory

The following subsections describe a possible approach. It has not been finalized.

#### AI memory and propagation

How the AI remembers and thinks about things — and how that memory interacts with future prompts — will need to be decided. The AI will need some concept of memory throughout any particular game, so that it can make decisions based on past decisions. But more broadly, it should also remember or be molded by entirely different play sessions and interactions with the player

##### Master memory class

Memory will be contained in a master class, which represents everything the AI knows and thinks. Broadly speaking, this class will need to hold different types of memories and thoughts:

1. **Memories about a particular run through or save file of a game**

    * **Short-term, factual memories:** (1-2 sentences)
      * "We just tried to open the door."
      * "The orc attacked us."
      * "We used our fireball spell for 2 mana, hitting the orc for 5 hp."

    * **Medium-term analysis of situation** (2-3 sentences)
      * "We are trying to find a hammer. I should head to the general store to see if they sell them."
      * "We need to cross this bridge. There is a troll in the way. Out options are: Attack it, talk to it, and find another way around it.

    * **Long-term, broad strategic analysis** (6-8 sentences, multiple paragraphs)
      * "We are trying to defeat the Big Bad. The strategies we tried so far are... we failed at..."

2. **Memories about previous sessions of a game**
    * **Analysis of previous game sessions** (12-15 sentences)
      * "In this run we learned... in act 1 we encountered...

3. **Memories about interactions with the player**

    This needs to be decided as to how this will fit in, but these will help shape the personality of Ally. Tough battles and 'crazy' moments should persist. Things the player says to Ally should be remembered.

4. **Personality**

    This will be a synthesis of all other memory types, and will be fed into various prompts in order to flavor decisions. The exact mechanism needs to be decided.

## GUI

The tech stack and layout of the GUI will need to decided. Tkinter is an option, though a bit unwieldly. Other libraries should be considered. A web frontend via a local server may be an option.

Initial development will output to the terminal. Developing the GUI should only come once a solid foundation is in placce, or when a GUI would genuinly help the flow of development.
