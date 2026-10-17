<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="logo/melodarium-dark.svg">
    <img src="logo/melodarium-light.svg" width="320" alt="Melodarium logo: four flowing strands joined by three dots, above the word MELODARIUM">
  </picture>
</p>

# Melodarium — User Guide

*Every arrangement of the notes you pick, written as LilyPond scores.*

Melodarium takes a set of notes you choose, works out every possible ordering of them, and writes them out as sheet music. It produces LilyPond score files (`.ly`) and, with LilyPond, engraved PDFs. You can also have it save plain-text lists.

Melodarium is free software by Joshua Nichols, released under the GNU General Public License, version 3 or later. The source code is at [github.com/joshdnichols/Melodarium](https://github.com/joshdnichols/Melodarium). See [section 13](#13-licenses-and-acknowledgements) for details.

---

## Contents

1. [What it does](#1-what-it-does)
2. [Starting the app](#2-starting-the-app)
3. [Quick start](#3-quick-start)
4. [The control panel at a glance](#4-the-control-panel-at-a-glance)
5. [Settings reference](#5-settings-reference)
6. [Advanced settings](#6-advanced-settings)
7. [Running a job: Start, Pause, Stop, Resume, Reset](#7-running-a-job-start-pause-stop-resume-reset)
8. [Preview and engraving PDFs](#8-preview-and-engraving-pdfs)
9. [Where the files go and what they are](#9-where-the-files-go-and-what-they-are)
10. [Reading the scores](#10-reading-the-scores)
11. [How big will it be?](#11-how-big-will-it-be)
12. [Troubleshooting](#12-troubleshooting)
13. [Licenses and acknowledgements](#13-licenses-and-acknowledgements)
14. [Glossary](#14-glossary)

---

## 1. What it does

You choose:

- **which notes** to use, from the 12 chromatic pitches;
- **how many notes** make up one permutation (2 to 24);
- whether notes **may repeat**.

The app then lists **every** arrangement in alphabetical (lexicographic) order. For example, A, B, C, D taken 4 at a time with repeats allowed gives `A A A A`, `A A A B`, `A A A C` and so on up to `D D D D`, which is 256 arrangements.

Each arrangement becomes **one measure** of music. The time signature (hidden) equals the number of notes, and the stems are hidden. The measures are laid out on letter-size pages and split into files and PDFs of the sizes you choose.

The app saves its progress constantly. You can pause, stop, quit or even lose power, and it picks up exactly where it left off.

---

## 2. Starting the app

The app opens **in its own window**.

| How you have it | How to start it |
|---|---|
| **Windows app** | Open the `Melodarium` folder and double-click **Melodarium.exe**. |
| **Mac app** | Open **Melodarium** from Applications. |
| **Python script** | Run `python melodarium.py` (Windows: `py melodarium.py`). It uses its own window when pywebview is installed (`pip install pywebview`). |

**When it opens in your web browser instead:** the app always opens, but it uses the browser when its own window isn't possible. A one-line note at the top of the panel says why and how to get the window:

- **WebView2 is missing (Windows):** the window uses Microsoft's **WebView2 Runtime**, which comes with Windows 11 and current Windows 10. If it's missing, the note links to Microsoft's free download. Install it and reopen the app.
- **pywebview isn't installed:** when running the Python script, the note gives the command to install it.
- **The window failed to start for any other reason:** the note says so.

Everything works the same in the browser. The panel is at `http://127.0.0.1:8765`; if the browser doesn't open by itself, type that address in. To always use the browser, start the app with `--browser`.

**Opening the app again while it's running** brings its window forward (or the browser panel back). It never starts a second copy.

**Quitting:** close the window, or use the **Quit** button at the top right of the panel (on a Mac, also **Melodarium → Quit**). Progress is saved first, and **Resume** continues where you left off. In browser mode, closing the tab leaves the app running in the background; use **Quit**.

### First launch on another computer

The apps are not code-signed (see the build instructions), so the operating system warns the first time:

- **Windows:** "Windows protected your PC" → **More info** → **Run anyway**.
- **Mac:** "cannot be opened" or "Apple could not verify…" → open **System Settings → Privacy & Security**, scroll down, and click **Open Anyway**. The Mac app also asks once for access to the Documents folder; click **OK**.

---

## 3. Quick start

1. **Notes per permutation:** drag the slider, for example to **4**.
2. **Notes to use:** tick the notes, for example **A B C D**.
3. Check the **summary** line under the settings, for example *"256 permutations · about 6 pages in 1 PDF · about 5.0 KB · 1 file"*.
4. Optional: press **Preview first page** to see the first page engraved.
5. Press **Start**. The score files are written.
6. When it says it's finished, press **Engrave PDFs**. LilyPond turns the score files into PDFs.
7. The files are in the folder shown next to **Finished files**.

> **Important:** **Start** writes LilyPond score files (`.ly`). The **PDFs** come from the second step, **Engrave PDFs**. See [section 8](#8-preview-and-engraving-pdfs).

---

## 4. The control panel at a glance

On a wide window the panel has two columns: **settings on the left**, and the **run panel on the right**, which stays in view while you scroll. On a narrow window the run panel comes after the settings.

**Top of the page:** the logo, the **Acknowledgements** link (licenses) and **Quit**. **Click the logo to switch between dark and light mode.** The panel starts in your computer's own setting each time it opens; a choice made with the logo lasts until you close the app. Under it, a slim **Preset** row loads, deletes and saves presets. At the very bottom, a small line gives Melodarium's copyright and license, with a link to its source code.

**Settings, in five numbered steps:**

| Step | What's in it |
|---|---|
| **1 Notes** (always open) | Notes per permutation, sharps or flats, the note buttons, the two repeat options, and **Only part of the list…**, which opens the Range boxes. It opens by itself when a run uses a range. |
| **2 Notation** | Clef, octave, same octave or nearest, chunk labels on or off. |
| **3 Pages** | Staff size, the two systems sliders, pages per PDF, PDF links. |
| **4 Files & saving** | Save location, max file size, plain-text lists. |
| **5 Advanced** | LilyPond program and version, enharmonic spellings, the repeated-accidental option, text and music fonts, output to outline. It opens by itself if LilyPond isn't found. |

Steps 2–5 open with a click. When closed, each shows a one-line summary of its settings, such as *staff 20 · 10 / 12 systems · 100 pages per PDF · no links*.

**Explanations:** point at a small **ⓘ** next to a setting, or tab to it, to read what the setting does. Warnings appear only when they apply: the caution for custom music fonts, the outline file-size warning, too many systems, low disk space.

**The run panel:**
- the **summary**: permutations, pages, PDFs, size and files;
- **Start** (or **Resume** / **Start new run**), with **Pause**, **Stop** and **Reset** under it;
- the progress bar with the status, plus elapsed time, current chunk and files finished, and the latest message;
- **Preview first page** and **Engrave PDFs**. **Stop engraving** appears while engraving. The preview opens in a separate window; **Open it again** reopens it;
- **Latest bars** and **Finished files** (with the run folder's path), each of which opens and closes with a click.

---

## 5. Settings reference

### Presets

At the top of Settings. Save all current settings under a name, then load or delete them later.

- **Save:** type a name, then press **Save**.
- **Load:** pick a preset from *Saved presets…*, then press **Load**.
- **Delete:** pick it, then press **Delete**.

Presets are stored in `presets.json`, in the same place as the app's progress file (see [section 9](#where-the-app-keeps-its-own-files)).

### Notes per permutation

Slider, **2 to 24**, default 4. This is how many notes make up one permutation, which is also the length of each measure.

- Above 12, a red warning appears: *"Warning! File sizes get exponentially bigger beyond this point!"*
- From **18** notes upward, each permutation is split evenly over **two lines**, with no barline at the split.

### Accidentals

- **Sharps (is):** A, A♯, B, C, C♯, D, D♯, E, F, F♯, G, G♯
- **Flats (es):** A, B♭, B, C, D♭, D, E♭, E, F, G♭, G, A♭

The "is" and "es" names are LilyPond's Dutch note names (`ais` = A♯, `bes` = B♭). Switching between sharps and flats keeps the same pitches ticked.

### Notes to use

Tick the notes to include. **Select all** and **Select none** are shortcuts. The count beside the heading shows how many are ticked.

The note order is always A, A♯/B♭, B, C … G♯/A♭. The octave runs from the A below the chosen C up to the G♯ above it (see [Octave](#octave)).

### Repeat options

Two tick boxes below the notes. You can tick one of them or neither.

| Option | Rule | Count for *n* notes, length *k* |
|---|---|---|
| *(neither ticked)* | Any note may appear any number of times | *n*<sup>*k*</sup> |
| **Exclude repeated notes** | No note twice **in a row** | *n* × (*n* − 1)<sup>*k*−1</sup> |
| **Use each note once** | No note repeated **anywhere**; needs at least *k* ticked notes | *n*! / (*n* − *k*)! |

The count of permutations is shown in brackets next to the options. When one of these options is on, the title of every score gets a suffix: **"– Excluding Repeated Notes"** or **"– Using Each Note Once"**.

### Range

Generate only part of the full list, from a **Start** permutation to an **End** permutation, both included.

- Each row has one small box per note. Type a note name into each box (`a`, `ais`, `bes`…); the cursor moves on by itself, and letters that don't fit are refused.
- If the ending comes before the start, or a box holds a note you haven't ticked, a red message says *"Permutation not possible…"*.
- **Reset to full range** sets Start to the first permutation and End to the last.
- **Measure numbers always count from the full list.** If your range starts at permutation 39,155, the first measure is numbered 39155.

### Clef

**G (treble)**, **F (bass)**, **Tenor** or **Alto**.

### Octave

Five choices, in LilyPond's octave marks: **c,** · **c** · **c'** · **c''** · **c'''**. `c'` is middle C (C4); each step is one octave.

The chosen C sets the octave block: notes run from the **A a third below that C** up to the **G♯ above it**. With `c'`, an A is the A just below middle C.

### Note placement

- **Same octave:** every note name always has the same absolute pitch, inside the chosen octave block. With `c'` that is A3 up to G♯4: every A is the A below middle C, every G♯ the one above it.
- **Nearest (within a 4th):** each measure starts in the chosen octave, and every following note goes to whichever octave is nearest the previous note (a fourth or less, counted by letter name, as in LilyPond's `\relative`).

The subtitle of every score ends with **"– same octave"** or **"– nearest within a 4th"**.

### Chunk labels

Tick box, **on** by default. Prints a label above the staff wherever a new block of the list begins: for example **A B × ×** marks the start of all permutations beginning A B (see [section 10](#10-reading-the-scores)). Untick it for scores without these labels. The `.ly` files keep a comment at each block, so they're still easy to find in the file.

### Staff size

Slider, **10 to 30**, default **20** (LilyPond's standard). This scales everything: notes, staff, measure numbers and spacing.

### Systems on the first page / Systems on the other pages

Two sliders, **1 to 12** each. The defaults are **10** for each PDF's first page, which also carries the title block, and **12** for the pages after it.

How many **measures** fit on one line depends on the permutation length:

| Notes per permutation | Measures per line |
|---|---|
| 2 | 6 |
| 3–4 | 4 |
| 5–6 | 2 |
| 7–17 | 1 |
| 18–24 | 1 measure over 2 lines |

If you ask for more systems than fit at the current staff size, a warning gives an estimate of how many will fit. Too many systems make LilyPond add extra pages, so PDFs come out longer than *Pages per PDF*.

Systems that fit on a letter page, as measured with LilyPond 2.26:

| Staff size | Same octave: first page / other pages | Nearest: first page / other pages |
|---|---|---|
| 10–16 | 12 / 12 | 12 / 12 |
| 18 | 12 / 12 | 11 / 12 |
| 20 | 12 / 12 | 10 / 11 |
| 22 | 10 / 11 | 9 / 10 |
| 24 | 9 / 10 | 8 / 9 |
| 26 | 8 / 9 | 7 / 8 |
| 28 | 8 / 9 | 6 / 8 |
| 30 | 7 / 8 | 6 / 7 |

### PDF links

LilyPond's **point-and-click** links: clicking a note in the PDF opens the matching line of the `.ly` file in a text editor that supports it.

- **No links** (default): the smallest PDFs.
- **Links on notes:** only the notes are clickable.
- **All links:** every element is clickable.

Links make PDFs bigger and store the run folder's path inside them.

### Pages per PDF

**1 to 10,000**, default **100**. Each PDF is one LilyPond *book*. A PDF may have fewer pages when a score file ends first. Large values make LilyPond use more memory while engraving.

### Max file size

Slider, **500 to 1,500 KB**, default **1,000 KB**. Each `.ly` score file is closed and a new one started before it would pass this size. Plain-text lists (if turned on) are split at the same size; a list that never reaches it stays one file.

### Save to

- **Next to this program** (default; the label may read *In Documents › Melodarium*): see [section 9](#9-where-the-files-go-and-what-they-are).
- **Another folder:** type a path or press **Browse…**.

Each run creates its own subfolder there.

### Plain-text lists

**Also save plain-text lists (.txt)**: one permutation per line, no LilyPond. Split at the same size limit as the score files.

---

## 6. Advanced settings

Click **Advanced** at the bottom of Settings to open it.

### LilyPond program

Shows which LilyPond the app uses and where it came from:

- **bundled:** the copy built into the Windows/Mac app;
- **installed:** a LilyPond found on your computer;
- **your setting:** a path you entered.

To use a different LilyPond, type the path to its `lilypond` (or `lilypond.exe`) program and press **Use this**. **Find automatically** goes back to the automatic search.

### LilyPond version

**2.26 or newer** (default) or **2.24**. This only changes the syntax the `.ly` files are written in, mainly for fonts and spacing. Use 2.24 only if you will engrave the files yourself with LilyPond 2.24.

### Enharmonic spellings

Tick any of these to use the spelling on the left instead of the usual note:

| Tick | Replaces |
|---|---|
| **ces** (C♭) | B |
| **fes** (F♭) | E |
| **bis** (B♯) | C |
| **eis** (E♯) | F |

### Don't repeat the accidental on an immediately repeated note

When the same note appears twice in a row, the second accidental is hidden: A♯ A♯ prints as A♯ A. Its space is kept, so every measure stays the same width.

> Every note normally shows its accidental (natural, sharp or flat), and all accidentals get the same width. That way every measure is spaced identically, and the last line of each file is padded to match.

### Text font

The font for titles, measure numbers and the footer. Start typing to choose from the fonts on your computer; the line below confirms whether the font was found. Leave it blank for LilyPond's default (C059, a Century Schoolbook design).

Text fonts are **not** bundled with the app. They come from your own computer and are used under their own licenses.

### Music font

The font for noteheads, clefs and accidentals. Leave it blank for **Emmentaler**, LilyPond's own font. The bundled alternatives are:

> beethoven · cadence · gonville · gutenberg1939 · haydn · improviso · lilyboulez · lv-goldenage · paganini · profondo · ross · scorlatti · sebastiano

Pick one from the list. The line below shows **✓ Installed in LilyPond** or a warning if LilyPond doesn't have it. Capitals don't matter: "Cadence" is corrected to "cadence". A caution note reminds you that custom music fonts need LilyPond 2.24 or newer.

### Output music to outline

When ticked, every **music symbol** is drawn as a vector shape instead of being stored as a font inside the PDF. Text (titles, measure numbers, footer) keeps its font and stays selectable and searchable. The PDFs look identical.

- **Warning shown in the panel:** *"Makes PDFs about 5 to 10 times larger: roughly 80–150 KB per page instead of about 16 KB, so a 100-page PDF can reach 15 MB."*
- **Required for Cadence:** Cadence is licensed under the GPL without a font exception, so the box is ticked automatically when Cadence is chosen and can't be unticked. The panel says *"Required for cadence (GPL font)…"*.
- **Safety check:** after engraving, the app checks every PDF. If outlining didn't take effect, so the music font ended up embedded, that PDF is deleted and the problem is reported.

---

## 7. Running a job: Start, Pause, Stop, Resume, Reset

| Button | What it does |
|---|---|
| **Start** | Checks the settings and begins writing score files. Settings are locked while the run is unfinished. After a run completes, the button reads **Start new run**. |
| **Pause** | Halts at once and saves. Press **Resume** (the Start button) to continue. |
| **Stop** | Saves and ends the session. **Resume** continues exactly where it stopped. |
| **Reset** | Forgets the saved progress so you can change settings and start over. You are asked to confirm. Files already written are **not** deleted. |

Before starting, the app may ask you to confirm:

- a text font that wasn't found on your computer;
- the caution note for a custom music font;
- low free disk space for the estimated size;
- a run larger than about 5 GB.

### While it runs

- The **progress bar and counts** show permutations written out of the total.
- **Elapsed** is the running time, excluding paused time.
- **Computing chunk** shows which block of the list is being written, for example `A B × ×`, meaning all permutations starting A B.
- **Files finished** counts the score files completed.
- **Latest bars** lists the last permutations written.
- **Finished files** lists each completed file. The one being written is marked *(writing)*.

### Interruptions are safe

Progress is saved about once a second in `progress.json`. If the app closes unexpectedly, or the computer restarts, open the app again and press **Resume**. Anything written after the last save is trimmed off and rewritten, so nothing is duplicated or lost.

---

## 8. Preview and engraving PDFs

### Preview first page

Engraves just the **first page** with the current settings and opens it in **a separate window** (another app window, or a browser window in browser mode), sized to read the page comfortably. Each new preview replaces the previous preview window. It's a quick way to check clef, octave, fonts, staff size and layout before a big run. The preview is stored in a temporary folder, not in your output folder. LilyPond warnings, if any, are listed in the panel under **Preview · first page**, with an **Open it again** link. If the browser blocks the window, allow pop-ups for the panel's page.

### Engrave PDFs

After a run finishes (or after you stop it), press **Engrave PDFs**. LilyPond engraves the score files **one at a time**, which keeps its memory use low. The line under the buttons shows *"Engraving 3 of 12: … · 00:01:20"*, and then a summary when it finishes.

- **Files already engraved are skipped.** A score file whose PDFs all exist and are newer than it counts as "already up to date". To redo a file, delete its PDFs.
- **Stop engraving** stops at once. The file being engraved is left unfinished and is redone next time.
- **If a file fails,** the panel shows:
  - the reason in plain words;
  - LilyPond's exit code;
  - the last meaningful lines from LilyPond;
  - the name of a `.log` file holding LilyPond's full output (it sits next to the score file).

  See [Troubleshooting](#12-troubleshooting).

### Engraving outside the app

Each run folder also contains:

- **`engrave_all.bat`** (Windows) and **`engrave_all.command`** (Mac): double-click to engrave every score file, one at a time, with the same LilyPond the app uses.
- **`master.ly`**: includes every score file of the run, to engrave everything in **one** LilyPond run (`lilypond master.ly`, run inside the folder). That's fine for small runs; for large ones use the scripts above.

---

## 9. Where the files go and what they are

### The run folder

Each run gets its own folder inside the save location. Its name describes the settings, for example:

```
len4-abcd-treble-c4
len8-abcd-bass-c3-norepeat-nearest-staff24
len6-acegis-treble-c4-from-101-to-5000
len24-chromatic-treble-c4-from-79496847203390844133441525-count-12
```

| Part | Meaning |
|---|---|
| `len4` | notes per permutation |
| `abcd` | the ticked notes; `chromatic` (or `chromatic-flats`) when all 12 are ticked |
| `treble` | clef |
| `c4` | octave (`c2` … `c6`; `c4` is middle C) |
| `-norepeat` / `-once` | repeat option |
| `-nearest` | nearest-octave placement |
| `-staff24` | staff size, when not 20 |
| `-from-101-to-5000` | a range: first and last permutation numbers. When the numbers are very long, the end is given as a count instead (`-from-…-count-12`). |

### The default save location

| Running as | Default location |
|---|---|
| Python script | The folder `melodarium.py` is in |
| Windows app | The app's own folder, or **Documents\Melodarium** if that folder can't be written to (for example in Program Files) |
| Mac app | **Documents/Melodarium** |

The full path of the current run folder is shown next to **Finished files**.

### What's inside a run folder

| File | What it is |
|---|---|
| `aaaa-bdca.ly` | A LilyPond **score file**, named by its first and last permutation (notes run together; `ais`, `bes`… stay as written). |
| `aaaa-bdca.pdf` | An **engraved PDF**, named by the permutations it contains. One score file can produce several PDFs (one per *Pages per PDF*). |
| `index.csv` | One row per PDF: name, first and last permutation, first and last measure number, first and last page number. |
| `aaaa-bdca.txt` | Plain-text list, if turned on: one permutation per line. |
| `cc0-80x15.eps` | The CC0 badge printed in each page's footer. Keep it with the `.ly` files. |
| `master.ly` | Includes every score file (see [section 8](#engraving-outside-the-app)). |
| `engrave_all.bat` / `.command` | Engrave-everything scripts for Windows and Mac. |
| `aaaa-bdca.log` | Only after a failed engraving: LilyPond's full output for that file. |
| `_in_progress.ly` / `.txt` | The file being written right now. It is renamed when finished. |

### Shortened file names (very long permutations on Windows)

Windows limits a file's full path to 260 characters. A file name holds two permutations, and with long permutations that alone can pass the limit: 24 notes such as `gis` take 72 characters each. When the full names won't fit, the app automatically shortens the **second** permutation to its last few notes, like a page range written "1234–56":

```
gisgisgis…gisaaisb-gisgis.pdf    (first permutation in full, then the last notes of the last one)
```

To keep that unambiguous, a file also closes wherever the notes before that ending change, so everything in a file shares the same opening. Files may therefore be a little smaller than *Max file size*. `index.csv` always lists the first and last permutation of each PDF in full. Normal runs, and runs on a Mac, are not affected.

If even shortened names won't fit, the app says so before starting; choose a save folder with a shorter path, such as `C:\Perm`.

### Where the app keeps its own files

These live in the default save location:

- `progress.json`: the progress memory;
- `presets.json`: saved presets;
- `config.json`: app settings such as a LilyPond path you entered.

---

## 10. Reading the scores

### Page layout

US Letter (8.5 × 11 in), no first-line indent.

### First page of each PDF

| Element | Example |
|---|---|
| **Title** | Note Permutations *(– Excluding Repeated Notes / – Using Each Note Once)* |
| **Subtitle** | 4-note permutations of A, B, C, D *– same octave / – nearest within a 4th* |
| **Range line** (first PDF of each score file) | A A A A to D C B A, centered; a long range goes on two centered lines |

The title, subtitle and range line are always centered. If one is too wide for the page (long suffixes, many notes, large staff sizes) it breaks into several centered lines: for example the title becomes *Melodarium* over *Using Each Note Once*.

### The music

- **One measure = one permutation.** Stems and the time signature are hidden.
- **Measure numbers** (italic, above the staff) are the **permutation's number in the full list**, so measure 57 is the 57th arrangement. They're written:
  - in full below one million: **57**, **999999**;
  - in millions with six decimals below one billion: **1.000001M** for 1,000,001;
  - in full, in groups of three, from one billion up: **79 496 847 203 390 844 133 441 525**. Numbers that large only occur with 9 or more notes, where each line holds one measure.

  A number at the start of a line begins at the left margin; the others are centered on their barline. LilyPond moves each number up as needed to clear high notes and accidentals.
- **Chunk labels** (unless turned off under **Notation**) above the staff mark where a new block of the list begins, for example **A B × ×**: every permutation that starts with A B. The × means "any note".
- **Barlines** between measures are thick. With 18 or more notes, each permutation is split over two lines with no barline at the split.
- **The last line** of a file is padded with invisible measures, so its measures are exactly as wide as everywhere else.

### Footer on every page

The CC0 badge and *"CC0 1.0 Universal (public domain dedication)"*, with a link to the CC0 deed. Page numbers continue across all the PDFs of a run.

---

## 11. How big will it be?

Counts grow very fast. The summary line always shows the exact number before you start.

**All 12 notes:**

| Length | Repeats allowed | Exclude repeated notes | Use each note once |
|---|---|---|---|
| 3 | 1,728 | 1,452 | 1,320 |
| 4 | 20,736 | 15,972 | 11,880 |
| 5 | 248,832 | 175,692 | 95,040 |
| 6 | 2,985,984 | 1,932,612 | 665,280 |
| 8 | 429,981,696 | 233,846,052 | 19,958,400 |
| 12 | about 8.9 × 10¹² | about 3.4 × 10¹² | 479,001,600 |

**Rules of thumb:**

- One page holds about 6 to 72 permutations, depending on length and systems per page (48 for 3–4 notes at 12 systems).
- A normal PDF page is about 16 KB. With *Output music to outline* it is 80–150 KB.
- Use **Range** to work through huge sets in parts.
- Writing score files is fast. **Engraving is the slow part**, so for big runs engrave in stages: stop, engrave, resume.

---

## 12. Troubleshooting

| Problem | What to do |
|---|---|
| **I don't see any PDFs** | **Start** only writes `.ly` files. Press **Engrave PDFs** after the run finishes. The PDFs land in the run folder shown next to *Finished files*. |
| **"Couldn't save … .pdf: it is probably open in a PDF viewer…"** | Close that PDF (and any browser tab showing it), then press **Engrave PDFs** again. Windows can't replace an open file. |
| **"Even shortened, file paths would be about … characters"** (Windows) | Choose a save folder with a shorter path, such as `C:\Perm`. Names are already shortened automatically (see [section 9](#shortened-file-names-very-long-permutations-on-windows)). |
| **"LilyPond ran out of memory"** | Lower **Pages per PDF** or **Max file size**, then run and engrave again. |
| **"The music font … isn't installed"** | Choose a font marked ✓ in the list, or leave Music font blank. |
| **"Output to outline didn't take effect…"** | The affected PDFs were deleted. Engrave again. If it repeats, the LilyPond in use doesn't support it; use the bundled LilyPond. |
| **"LilyPond stopped without any message"** | Antivirus may have closed it, or memory ran out. Try again with smaller PDFs; check the `.log` file. |
| **"Preview and Engrave need LilyPond"** | Open **Advanced** and press **Find automatically**, or enter the path to `lilypond` / `lilypond.exe`. |
| **A page has extra pages or looks squeezed** | Too many systems for the staff size. Lower the **Systems** sliders until the warning disappears. |
| **The panel says "Lost contact with the program"** | The app was closed. Open it again. Progress is kept. |
| **The panel opened in the browser, not its own window** | Read the note at the top of the panel. On Windows it's usually the missing WebView2 Runtime: follow the link, install it, reopen the app. |
| **The browser didn't open** (browser mode) | Go to `http://127.0.0.1:8765`. |
| **I can't change settings** | A run is unfinished: finish it, or press **Reset** to start over (files already written are kept). |
| **Browse… doesn't open a window** | Type the folder path instead. On Windows the folder window can open behind the browser, so check the taskbar. |

---

## 13. Licenses and acknowledgements

### Melodarium's license

Melodarium is Copyright © 2026 Joshua Nichols. It is free software: you can use, share and change it under the terms of the [GNU General Public License](https://www.gnu.org/licenses/gpl-3.0.html), version 3 or (at your option) any later version. It comes with **no warranty**, to the extent permitted by law.

- **What's covered:** the program, the build scripts, this guide, and the Melodarium name artwork, logo and icons.
- **Source code:** [github.com/joshdnichols/Melodarium](https://github.com/joshdnichols/Melodarium). The Windows and Mac downloads also include it, as `Melodarium-source.zip` in their source folder.
- **The license text:** `LICENSE.txt` next to the app, and on the Acknowledgements page. `NOTICE.txt` has the copyright notice and the additional permission below.
- **If you share a changed version:** keep the copyright and license notices, and share your changed source code with it, under the same license.

### Your scores

Your scores carry a **CC0 1.0** public domain dedication, printed in each page's footer. Melodarium copies some of its own code into each score (for measure numbers, labels and outlined music). An **additional permission** in Melodarium's license puts that code under CC0 too, as it appears in the files Melodarium makes, so the GPL never applies to your scores. Each `.ly` file says so in its first lines.

The CC0 badge is a Creative Commons trademark, used with a link to the deed.

### Acknowledgements

The **Acknowledgements** link (top right of the panel) shows Melodarium's own license first, then everything included, with its license text:

- **LilyPond** (GPL v3) and the programs it includes: Ghostscript, Guile and others, each with its own license file.
- **Music fonts:**
  - SIL Open Font License: Beethoven, Gutenberg1939, Haydn, Improviso, LilyBoulez, LV-GoldenAge, Paganini, Profondo (with Profondo Tuplet Numbers), Ross, Scorlatti, Sebastiano, and LilyPond's own Emmentaler.
  - Gonville: unrestricted use.
  - Cadence: GPL v2 or later, used only with output to outline.
- **Python** and **PyInstaller** (in the standalone apps).
- **pywebview**, which draws the app window, and the packages it needs: **pythonnet** and its helpers on Windows, **PyObjC** on a Mac, and **bottle**, **proxy_tools** and **typing_extensions**. These are listed with their versions and license files in the standalone apps.

Text fonts are not included; any you choose come from your own computer.

---

## 14. Glossary

| Term | Meaning |
|---|---|
| **Permutation** | One ordering of the chosen notes, for example `C A D B`. |
| **Measure / bar** | Here, exactly one permutation. |
| **System** | One line of music across the page. |
| **Chunk** | A block of consecutive permutations sharing their first notes (shown as `A B × ×`). |
| **Score file (`.ly`)** | A LilyPond text file describing the music. |
| **Engraving** | LilyPond turning a score file into a PDF. |
| **Book** | LilyPond's unit for one output PDF. |
| **Point-and-click** | PDF links from a note back to its line in the `.ly` file. |
| **Outline** | Drawing glyphs as shapes instead of embedding the font. |
| **Lexicographic order** | Dictionary order, following the note order A, A♯/B♭, B, C … G♯/A♭. |
