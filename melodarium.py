#!/usr/bin/env python3
"""
Note permutations with a small control panel, written as LilyPond scores.

In the panel you choose:
  - notes per permutation (2-12, slider)
  - sharps (ais, cis, ...) or flats (bes, des, ...)
  - which notes to use (any number of the 12)
  - Advanced: use ces / fes / bis / eis instead of b / e / c / f
  - where to save: next to this program (default) or another folder
  - optionally, plain-text lists of every permutation (.txt, one per line,
    split at the same size limit and named after their range)
  - clef (G / F / tenor / alto) and octave (c, c', c'')
  - maximum file size (500-1500 KB)
Every arrangement of the chosen notes (repeats allowed) is written as one
stemless bar per line, all notes in the chosen octave (LilyPond \\fixed:
c' means the octave from middle C up to the B above it). One permutation is
exactly one measure (time signature = number of notes, hidden). Scores are on
letter paper, 12 systems per page, with a fixed number of measures per system
(2 notes: 6, 3-4 notes: 4, 5-6 notes: 2, 7+ notes: 1), proportional spacing,
chunk labels, and a measure number centred over every barline. Measure N is
always permutation N of the full set, even in a ranged run; from one million
up, numbers are shown in millions with six decimals (1,234,567 -> 1.234567M).

Files split at the size limit and are named after their range, e.g.
a_a_a_a-c_b_d_b.ly. Each run's folder also gets master.ly, which combines
every finished file into one PDF:   lilypond master.ly
Progress is remembered in progress.json, so a stopped run resumes.

Run:   python melodarium.py      (the panel opens in your browser)
Quit:  close the terminal window or press Ctrl+C there (progress is saved).

Start  - begin with the chosen settings, or continue after Pause / Stop
Pause  - hold in place (Start continues instantly)
Stop   - end this run and save to progress.json (Start, or a later launch, resumes)
Reset  - forget progress so the settings can be changed
"""

import glob
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---------------- settings ----------------
NOTE_SETS = {   # the same 12 pitches, spelled with sharps (is) or flats (es)
    "sharps": ["a", "ais", "b", "c", "cis", "d", "dis", "e", "f", "fis", "g", "gis"],
    "flats":  ["a", "bes", "b", "c", "des", "d", "ees", "e", "f", "ges", "g", "aes"],
}
SPELLINGS = {"sharps": "Sharps (is)", "flats": "Flats (es)"}
ENHARMONICS = {"ces": "b", "fes": "e", "bis": "c", "eis": "f"}  # Advanced: use X instead of Y
WINDOWS_PATH_LIMIT = 255       # Windows' 260-character path limit, with a little room to spare
MIN_LEN, MAX_LEN = 2, 24        # slider range: notes per permutation
SPLIT_FROM = 18                 # from this length each permutation is split over two lines
MIN_PAGES_PDF, MAX_PAGES_PDF = 1, 10000   # pages per PDF (each PDF is one LilyPond \\book)
MIN_KB, MAX_KB = 500, 1500      # slider range: max file size
MIN_STAFF, MAX_STAFF = 10, 30   # slider range: staff size (LilyPond's default is 20)
# Measure numbers: italic, relative size (scales with the staff size).
# -1.74 gives 9 pt at the default staff size of 20.
BAR_NUMBER_FONT_SIZE = -1.74
CLEFS = {"treble": "G (treble)", "bass": "F (bass)", "tenor": "Tenor", "alto": "Alto"}
PITCHES = ["c,", "c", "c'", "c''", "c'''"]   # octave choices, low to high
PLACEMENTS = {"fixed": "Same octave", "nearest": "Nearest (within a 4th)"}
# scientific octave of each choice: c' is middle C (C4), "c" the C below it (C3)
OCTAVE_NUMBER = {"c,": 2, "c": 3, "c'": 4, "c''": 5, "c'''": 6}
LETTER_STEP = {"c": 0, "d": 1, "e": 2, "f": 3, "g": 4, "a": 5, "b": 6}
DEFAULT_SETTINGS = {"length": 4, "notes": ["a", "b", "c", "d"], "max_kb": 1000, "staff_size": 20,
                    "pages_per_pdf": 100, "repeat_mode": "all", "pdf_links": "off",
                    "systems_per_page": 12, "first_page_systems": 10, "text_font": "", "music_font": "", "lilypond": "2.26",
                    "outline_fonts": False, "chunk_labels": True,
                    "spelling": "sharps", "enharmonics": [], "save_to": "", "write_txt": False,
                    "clef": "treble", "pitch": "c'", "placement": "fixed", "no_repeat_acc": False}
def app_folder():
    """The folder this program lives in: the .py file's folder, or - once packaged
    as an app - the folder holding the .exe (Windows) or the .app (Mac)."""
    if getattr(sys, "frozen", False):
        exe = os.path.abspath(sys.executable)
        parts = exe.split(os.sep)
        for k in range(len(parts) - 1, 0, -1):     # Mac: .../Name.app/Contents/MacOS/Name
            if parts[k].endswith(".app"):
                return os.sep.join(parts[:k]) or os.sep
        return os.path.dirname(exe)
    return os.path.dirname(os.path.abspath(__file__))


SCRIPT_DIR = app_folder()
# files packaged inside the app (PyInstaller puts them in sys._MEIPASS)
RESOURCE_DIR = getattr(sys, "_MEIPASS", SCRIPT_DIR)
# Mac app: things copied into Name.app/Contents/Resources after the build (LilyPond)
BUNDLE_RESOURCES = (os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(sys.executable)),
                                                  "..", "Resources"))
                    if getattr(sys, "frozen", False) and sys.platform == "darwin" else RESOURCE_DIR)
APP_NAME = "Melodarium"


def _writable(folder):
    try:
        os.makedirs(folder, exist_ok=True)
        probe = os.path.join(folder, ".write-test")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def data_folder():
    """Where progress, settings, presets and (by default) the scores are kept.
    Running from the .py file, or a Windows app in a folder you can write to: next to
    the program. The Mac app (which lives in Applications), or a Windows app installed
    somewhere read-only like Program Files: Documents/Melodarium."""
    if getattr(sys, "frozen", False):
        if sys.platform != "darwin" and _writable(SCRIPT_DIR):
            return SCRIPT_DIR
        docs = os.path.join(os.path.expanduser("~"), "Documents")
        base = docs if os.path.isdir(docs) else os.path.expanduser("~")
        return os.path.join(base, APP_NAME)
    return SCRIPT_DIR


DATA_DIR = data_folder()
os.makedirs(DATA_DIR, exist_ok=True)
DEFAULT_PLACE = ("Next to this program" if DATA_DIR == SCRIPT_DIR
                 else "In Documents › " + APP_NAME if DATA_DIR.endswith(os.path.join("Documents", APP_NAME))
                 else "In your " + APP_NAME + " folder")
# Default save place is the folder this program is in; each run gets its own
# subfolder there (or in the folder chosen in the panel).
STATE_FILE = os.path.join(DATA_DIR, "progress.json")  # memory of what was done last
LILYPOND_VERSIONS = {"2.26": "2.26 or newer", "2.24": "2.24"}   # syntax differs (fonts, spacing)
# Measure numbers. LilyPond counts measures in a number type that stops near 2.1 billion,
# so each \score block restarts LilyPond's count at 1 and this formatter adds the block's
# first permutation number using Scheme's unlimited whole numbers. Shown as:
#   below 1,000,000 ............ 57
#   below 1,000,000,000 ........ 12.345678M  (millions, six decimals)
#   from 1,000,000,000 up ...... 79 496 847 203 390 844 133 441 525 (groups of three)
PERM_BAR_NUMBER = r"""% measure numbers: the permutation's number in the full list (see the notes in the app)
#(define (permBarNumber base)
   (lambda (barnum measure-pos alt-number context)
     (if (and (ly:moment? measure-pos)
              (ly:moment<? (ly:make-moment 0) measure-pos))
         (make-null-markup)   ; a line that starts mid-measure: no number
         (let ((n (+ base barnum -1)))
           (cond
            ((< n 1000000) (make-simple-markup (number->string n)))
            ((< n 1000000000)
             (make-simple-markup
              (string-append (number->string (quotient n 1000000)) "."
                             (string-pad (number->string (remainder n 1000000)) 6 #\0) "M")))
            (else   ; groups of three digits with a small gap between them
             (let loop ((digits (number->string n)) (groups '()))
               (if (<= (string-length digits) 3)
                   (make-line-markup (cons digits groups))
                   (loop (substring digits 0 (- (string-length digits) 3))
                         (cons (substring digits (- (string-length digits) 3)) groups))))))))))

"""
SCORE_TARGET = 480              # measures per \score block: keeps LilyPond's memory use modest
NOTE_LENGTH = "4"               # LilyPond duration: 4 = quarter notes
PAGE_EXTRA_PT = 10              # extra space under the page header and above the footer (on top of LilyPond's own)
FIRST_PAGE_EXTRA_PT = 8         # extra space under the first page's titles (on top of LilyPond's own)
MIN_SYSTEMS, MAX_SYSTEMS = 1, 12  # slider range: lines of music per page (default 12)
MUSIC_FONT_WARNING = "for Lilypond version 2.24.x and above! Proceed at your own caution!"
OUTLINE_WARNING = ("Makes PDFs about 5 to 10 times larger: roughly 80-150 KB per page "
                   "instead of about 16 KB, so a 100-page PDF can reach 15 MB.")
# Music fonts that may only be used with "output to outline": Cadence is GPL without a
# font exception, so its font data is never embedded in the PDFs (only drawn shapes).
OUTLINE_REQUIRED = {"cadence"}
# Put at the top of a score file when "output to outline" is on. Music symbols (noteheads,
# clefs, accidentals...) are drawn as vector shapes, so the music font is never embedded;
# text (titles, measure numbers, footer) keeps its embedded font and stays selectable.
#  - LilyPond writes every music symbol with its named-glyph routine; this replaces that
#    routine with one that calls lyOG, a small PostScript procedure.
#  - lyOG traces the symbol's outline (charpath) and fills it, instead of showing it as
#    font text. It is handed to Ghostscript just before the PDF is made.
#  - Text uses a different routine, so it is untouched.
# (LilyPond's own gs-never-embed-fonts option is NOT used: it leaves fonts out of the
# PDF without drawing them, so noteheads, clefs and accidentals disappear.)
OUTLINE_SNIPPET = r"""% Output music to outline (music font: @FONT@): music symbols are drawn as vector shapes,
% so the music font is not embedded in the PDF. Text keeps its font and stays selectable.
#(let ((out (resolve-module '(lily output-ps)))
       (lily (resolve-module '(lily))))
   (if (not (module-variable lily 'music-outline-installed))
       (let* ((table (and (module-variable out 'stencil-dispatch-alist)
                          (module-ref out 'stencil-dispatch-alist)))
              (entry (and table (assq 'named-glyph table)))
              (font-cmd (and (module-variable out 'ps-font-command)
                             (module-ref out 'ps-font-command)))
              (lyOG (string-append
                     "/lyOGc 64 dict def /lyOG { currentfont lyOGc 1 index known not { "
                     "dup dup length 1 add dict begin { 1 index /FID ne { def } { pop pop } ifelse } forall "
                     "/Encoding 256 array def currentdict end /LyOutlineFont exch definefont "
                     "lyOGc 3 1 roll put currentfont } if lyOGc exch get gsave setfont "
                     "currentfont /Encoding get 0 3 -1 roll put "
                     "currentpoint newpath moveto (\\000) false charpath fill grestore } bind def ")))
         (module-define! lily 'music-outline-installed #t)
         (if (and entry font-cmd)
             (begin
               ;; music symbols: outline them (fall back to normal if lyOG is missing)
               (set-cdr! entry
                 (lambda (font glyph)
                   (format #f "~a /~a /lyOG where {pop lyOG} {glyphshow} ifelse\n"
                           (font-cmd font) glyph)))
               ;; hand the lyOG procedure to Ghostscript ahead of the score
               (for-each
                (lambda (name)
                  (let ((v (module-variable lily name)))
                    (if (and v (variable-bound? v))
                        (let ((run-gs (variable-ref v)))
                          (variable-set! v (lambda (args ps)
                                             (run-gs args (string-append lyOG ps))))))))
                '(ly:gs-api ly:gs-cli)))))))
"""
OUTLINE_MARK_RE = r"% Output music to outline \(music font: ([^)]*)\)"


def pdf_font_names(path):
    """Names of the fonts embedded in a PDF (subset prefixes like ABCDEF+ removed)."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return set()
    return {m.decode("latin-1") for m in
            re.findall(rb"/FontName\s*/(?:[A-Z]{6}\+)?([^\s/\[\]<>()]+)", data)}


def music_font_embedded(path, music_font):
    """True if the PDF still embeds the music font (it should be outlines only)."""
    stem = (music_font or "emmentaler").lower()
    return any(n.lower() == stem or n.lower().startswith(stem + "-") for n in pdf_font_names(path))
CHUNK_DEPTH = 2                 # chunks group by the first 2 notes ("a b x x")
ROW_DELAY = 0.0                 # seconds to wait after each bar (e.g. 0.005 to watch it run)
PORT = 8765                     # control panel address: http://127.0.0.1:8765
# ------------------------------------------

# CC0 80x15 badge (Creative Commons "cc_zero.svg", small license badge from their
# official vocabulary design system), converted to vector EPS. It is saved in each
# run folder and placed in the footer with \epsfile.
CC0_EPS_NAME = "cc0-80x15.eps"
CC0_EPS = """%!PS-Adobe-3.0 EPSF-3.0
%%BoundingBox: 0 0 80 15
%%HiResBoundingBox: 0 0 80 15
%%Title: CC0 80x15 badge (Creative Commons)
%%Creator: converted from cc_zero.svg (creativecommons/vocabulary, license_badges/small)
%%Pages: 1
%%EndComments
save
10 dict begin
/m {moveto} bind def /l {lineto} bind def /c {curveto} bind def /h {closepath} bind def
newpath
0 15 m
80 15 l
80 0 l
0 0 l
h
1 setgray fill
newpath
80 15 m
80 0 l
0 0 l
0 15 l
80 15 l
79.25 14.25 m
0.75 14.25 l
0.75 0.75 l
79.25 0.75 l
79.25 14.25 l
h
0 setgray fill
newpath
22.797 13 m
23.8 11.405 24.39 9.523 24.39 7.499 c
24.39 5.476 23.801 3.595 22.798 2 c
80 2 l
80 13 l
22.797 13 l
h
12.42 12.969 m
9.283 12.969 8.494 10.01 8.494 7.5 c
8.494 4.99 9.281 2.031 12.42 2.031 c
15.557 2.031 16.344 4.99 16.344 7.5 c
16.344 10.01 15.557 12.969 12.42 12.969 c
h
12.42 10.906 m
12.547 10.906 12.662 10.886 12.772 10.859 c
12.999 10.666 13.108 10.396 12.893 10.021 c
10.803 6.183 l
10.738 6.67 10.729 7.145 10.729 7.5 c
10.729 8.605 10.807 10.906 12.42 10.906 c
h
13.982 9.137 m
14.093 8.549 14.109 7.934 14.109 7.5 c
14.109 6.395 14.033 4.094 12.42 4.094 c
12.293 4.094 12.176 4.106 12.066 4.133 c
12.046 4.139 12.027 4.147 12.005 4.154 c
11.974 4.164 11.939 4.174 11.907 4.185 c
11.548 4.339 11.321 4.615 11.647 5.105 c
13.982 9.137 l
h
0 setgray fill
newpath
21.229 11.152 m
20.764 12.304 20.086 13.324 19.194 14.218 c
18.907 14.504 18.607 14.759 18.302 15 c
14.594 15 l
15.842 14.652 16.961 13.991 17.948 13.002 c
18.684 12.266 19.247 11.426 19.632 10.486 c
20.017 9.546 20.21 8.55 20.21 7.5 c
20.21 5.316 19.464 3.506 17.983 2.059 c
17.212 1.313 16.348 0.739 15.387 0.342 c
15.043 0.199 14.693 0.091 14.341 0 c
18.233 0 l
18.569 0.257 18.897 0.529 19.205 0.834 c
20.1 1.705 20.775 2.705 21.226 3.834 c
21.691 4.977 21.919 6.197 21.919 7.5 c
21.92 8.789 21.691 10.01 21.229 11.152 c
h
6.957 2.025 m
6.211 2.771 5.635 3.615 5.228 4.552 c
4.832 5.503 4.628 6.482 4.628 7.499 c
4.628 8.528 4.831 9.515 5.228 10.454 c
5.634 11.403 6.21 12.257 6.957 13.015 c
7.916 13.996 9.021 14.654 10.268 15 c
6.58 15 l
6.289 14.765 6.004 14.516 5.732 14.238 c
4.816 13.324 4.117 12.279 3.631 11.113 c
3.156 9.959 2.92 8.756 2.92 7.5 c
2.92 6.232 3.156 5.029 3.631 3.887 c
4.106 2.745 4.795 1.717 5.699 0.801 c
5.994 0.51 6.305 0.248 6.623 0 c
10.503 0 l
10.158 0.088 9.817 0.191 9.484 0.328 c
8.547 0.723 7.705 1.289 6.957 2.025 c
h
0 setgray fill
newpath
30.514 7.264 m
30.235 7.031 29.836 6.914 29.317 6.914 c
28.324 6.914 l
28.324 5.197 l
27.333 5.197 l
27.333 9.972 l
29.383 9.972 l
29.856 9.972 30.232 9.849 30.513 9.603 c
30.794 9.357 30.935 8.975 30.935 8.459 c
30.934 7.896 30.794 7.497 30.514 7.264 c
h
29.753 8.983 m
29.626 9.089 29.449 9.142 29.222 9.142 c
28.324 9.142 l
28.324 7.736 l
29.222 7.736 l
29.45 7.736 29.626 7.794 29.753 7.908 c
29.879 8.022 29.942 8.204 29.942 8.452 c
29.942 8.701 29.879 8.878 29.753 8.983 c
h
31.733 9.972 m
32.748 9.972 l
32.748 7.039 l
32.748 6.711 32.786 6.472 32.864 6.321 c
32.984 6.053 33.247 5.92 33.651 5.92 c
34.053 5.92 34.315 6.054 34.435 6.321 c
34.512 6.471 34.551 6.711 34.551 7.039 c
34.551 9.972 l
35.565 9.972 l
35.565 7.037 l
35.565 6.529 35.486 6.135 35.329 5.851 c
35.036 5.332 34.476 5.074 33.651 5.074 c
32.825 5.074 32.264 5.333 31.969 5.851 c
31.812 6.134 31.733 6.529 31.733 7.037 c
31.733 9.972 l
h
40.085 9.463 m
40.231 9.26 40.304 9.017 40.304 8.734 c
40.304 8.442 40.23 8.208 40.083 8.031 c
40 7.931 39.879 7.841 39.719 7.759 c
39.962 7.671 40.146 7.53 40.27 7.338 c
40.394 7.146 40.457 6.913 40.457 6.639 c
40.457 6.356 40.386 6.102 40.244 5.878 c
40.154 5.729 40.041 5.604 39.906 5.502 c
39.754 5.385 39.574 5.306 39.367 5.262 c
39.159 5.219 38.934 5.198 38.692 5.198 c
36.54 5.198 l
36.54 9.972 l
38.848 9.972 l
39.43 9.963 39.842 9.793 40.085 9.463 c
h
37.492 9.143 m
37.492 8.09 l
38.652 8.09 l
38.86 8.09 39.028 8.129 39.157 8.208 c
39.287 8.287 39.351 8.427 39.351 8.627 c
39.351 8.85 39.265 8.996 39.094 9.067 c
38.947 9.117 38.759 9.142 38.531 9.142 c
37.492 9.142 l
h
37.492 7.3 m
37.492 6.027 l
38.651 6.027 l
38.858 6.027 39.019 6.055 39.134 6.111 c
39.343 6.215 39.447 6.414 39.447 6.708 c
39.447 6.956 39.346 7.127 39.143 7.22 c
39.03 7.272 38.871 7.298 38.665 7.301 c
37.492 7.301 l
h
41.313 9.972 m
42.311 9.972 l
42.311 6.056 l
44.695 6.056 l
44.695 5.198 l
41.313 5.198 l
41.313 9.972 l
h
46.275 5.197 m
45.284 5.197 l
45.284 9.972 l
46.275 9.972 l
46.275 5.197 l
h
47.665 9.473 m
48.05 9.866 48.539 10.063 49.133 10.063 c
49.928 10.063 50.509 9.799 50.876 9.272 c
51.079 8.976 51.188 8.679 51.203 8.381 c
50.205 8.381 l
50.142 8.61 50.06 8.783 49.961 8.9 c
49.783 9.107 49.52 9.211 49.171 9.211 c
48.816 9.211 48.535 9.065 48.33 8.773 c
48.125 8.481 48.022 8.066 48.022 7.531 c
48.022 6.996 48.13 6.594 48.346 6.328 c
48.563 6.061 48.838 5.928 49.172 5.928 c
49.514 5.928 49.775 6.042 49.954 6.272 c
50.054 6.395 50.136 6.58 50.201 6.826 c
51.192 6.826 l
51.106 6.305 50.888 5.883 50.537 5.556 c
50.186 5.229 49.735 5.067 49.186 5.067 c
48.506 5.067 47.972 5.288 47.583 5.728 c
47.194 6.17 47 6.777 47 7.548 c
47.002 8.379 47.224 9.021 47.665 9.473 c
h
54.797 9.868 m
55.132 9.758 55.403 9.556 55.61 9.262 c
55.777 9.025 55.89 8.768 55.951 8.491 c
56.012 8.214 56.042 7.951 56.042 7.701 c
56.042 7.066 55.914 6.528 55.659 6.088 c
55.313 5.494 54.779 5.197 54.057 5.197 c
51.998 5.197 l
51.998 9.972 l
54.057 9.972 l
54.354 9.967 54.601 9.933 54.797 9.868 c
h
52.968 9.143 m
52.968 6.027 l
53.89 6.027 l
54.361 6.027 54.69 6.259 54.875 6.723 c
54.977 6.978 55.027 7.282 55.027 7.633 c
55.027 8.119 54.951 8.492 54.798 8.752 c
54.645 9.012 54.343 9.143 53.889 9.143 c
52.968 9.143 l
h
60.466 5.621 m
60.106 5.25 59.584 5.064 58.902 5.064 c
58.22 5.064 57.698 5.25 57.338 5.621 c
56.855 6.077 56.612 6.733 56.612 7.591 c
56.612 8.466 56.854 9.122 57.338 9.561 c
57.698 9.932 58.22 10.118 58.902 10.118 c
59.584 10.118 60.106 9.932 60.466 9.561 c
60.947 9.123 61.188 8.466 61.188 7.591 c
61.188 6.733 60.947 6.077 60.466 5.621 c
h
59.842 6.347 m
60.074 6.639 60.191 7.053 60.191 7.591 c
60.191 8.126 60.075 8.54 59.842 8.833 c
59.611 9.126 59.297 9.271 58.902 9.271 c
58.507 9.271 58.191 9.125 57.956 8.834 c
57.721 8.542 57.603 8.128 57.603 7.59 c
57.603 7.052 57.72 6.638 57.956 6.346 c
58.191 6.055 58.507 5.909 58.902 5.909 c
59.297 5.909 59.61 6.056 59.842 6.347 c
h
65.116 9.972 m
66.552 9.972 l
66.552 5.198 l
65.623 5.198 l
65.623 8.427 l
65.623 8.52 65.624 8.65 65.626 8.817 c
65.628 8.985 65.629 9.114 65.629 9.205 c
64.725 5.198 l
63.755 5.198 l
62.857 9.205 l
62.857 9.114 62.858 8.985 62.86 8.817 c
62.863 8.65 62.864 8.52 62.864 8.427 c
62.864 5.198 l
61.934 5.198 l
61.934 9.972 l
63.385 9.972 l
64.254 6.218 l
65.116 9.972 l
h
68.84 9.972 m
69.969 9.972 l
71.658 5.198 l
70.576 5.198 l
70.262 6.179 l
68.503 6.179 l
68.18 5.197 l
67.136 5.197 l
68.84 9.972 l
h
68.774 7.001 m
69.997 7.001 l
69.395 8.88 l
68.774 7.001 l
h
73.175 5.197 m
72.184 5.197 l
72.184 9.972 l
73.175 9.972 l
73.175 5.197 l
h
74.093 9.972 m
75.139 9.972 l
77.034 6.643 l
77.034 9.972 l
77.964 9.972 l
77.964 5.198 l
76.967 5.198 l
75.024 8.586 l
75.024 5.198 l
74.094 5.198 l
74.094 9.972 l
h
1 setgray fill
end
restore
showpage
%%EOF
"""
BADGE_HEIGHT = 2.4             # staff spaces (the badge is 80 x 15, so about 12.8 wide)
COPYRIGHT_TEXT = "CC0 1.0 Universal (public domain dedication)"
CC0_DEED = "https://creativecommons.org/publicdomain/zero/1.0/"   # required with the CC0 badge

KB = 1000
STATE_VERSION = 10
FOOTER_RESERVE = 1500           # room kept for the closing part of each file
# Middle staff line for each clef: pitch of the invisible padding notes.
CLEF_MIDDLE = {"treble": "b'", "bass": "d", "alto": "c'", "tenor": "a"}


def note_set(spelling, enharmonics):
    """The 12 note names for a spelling, with any ticked enharmonics swapped in."""
    swap = {ENHARMONICS[e]: e for e in enharmonics}
    return [swap.get(n, n) for n in NOTE_SETS[spelling]]


def validate(raw):
    """Check settings sent from the panel. Returns (settings, error)."""
    try:
        length = int(raw["length"])
        max_kb = int(raw["max_kb"])
        staff_size = int(raw.get("staff_size", DEFAULT_SETTINGS["staff_size"]))
        systems = int(raw.get("systems_per_page", DEFAULT_SETTINGS["systems_per_page"]))
        first_systems = int(raw.get("first_page_systems", systems))
        pages_pdf = int(raw.get("pages_per_pdf", DEFAULT_SETTINGS["pages_per_pdf"]))
        text_font = str(raw.get("text_font", "") or "").strip()
        music_font = str(raw.get("music_font", "") or "").strip()
        lilypond = str(raw.get("lilypond", DEFAULT_SETTINGS["lilypond"]))
        chosen = set(raw["notes"])
        spelling = raw.get("spelling", DEFAULT_SETTINGS["spelling"])
        enharmonics = list(raw.get("enharmonics", []))
        save_to = str(raw.get("save_to", "") or "").strip()
        write_txt = bool(raw.get("write_txt", False))
        range_start = raw.get("range_start") or None
        range_end = raw.get("range_end") or None
        clef = raw.get("clef", DEFAULT_SETTINGS["clef"])
        pitch = raw.get("pitch", DEFAULT_SETTINGS["pitch"])
        placement = raw.get("placement", DEFAULT_SETTINGS["placement"])
        no_repeat_acc = bool(raw.get("no_repeat_acc", False))
        chunk_labels = bool(raw.get("chunk_labels", True))
        repeat_mode = str(raw.get("repeat_mode", "all"))
        pdf_links = str(raw.get("pdf_links", "off"))
        outline_fonts = bool(raw.get("outline_fonts", False))
    except (KeyError, TypeError, ValueError):
        return None, "Invalid settings."
    if spelling not in NOTE_SETS:
        return None, "Choose sharps or flats."
    if set(enharmonics) - set(ENHARMONICS):
        return None, "Unknown enharmonic option."
    enharmonics = [e for e in ENHARMONICS if e in enharmonics]
    names = note_set(spelling, enharmonics)
    if chosen - set(names):
        return None, "Those notes don't match the chosen spelling."
    notes = [n for n in names if n in chosen]  # keep the standard order
    if save_to:
        save_to = os.path.abspath(os.path.expanduser(save_to))
        if not os.path.isdir(save_to):
            return None, f"Save folder not found: {save_to}"
        if not os.access(save_to, os.W_OK):
            return None, f"Can't write to the save folder: {save_to}"
    if not MIN_LEN <= length <= MAX_LEN:
        return None, f"Notes per permutation must be {MIN_LEN}-{MAX_LEN}."
    if not notes:
        return None, "Tick at least one note."
    if pdf_links not in PDF_LINKS:
        return None, "Choose a PDF links option."
    if repeat_mode not in REPEAT_MODES:
        return None, "Unknown repeat option."
    if perm_count(len(notes), length, repeat_mode) == 0:
        return None, ("“Use each note once” needs at least as many ticked notes "
                      "as notes per permutation." if repeat_mode == "once" else
                      "“Exclude repeated notes” needs at least 2 ticked notes.")
    if clef not in CLEFS:
        return None, "Choose a clef."
    if pitch not in PITCHES:
        return None, "Choose an octave."
    if placement not in PLACEMENTS:
        return None, "Choose a note placement."
    if not MIN_KB <= max_kb <= MAX_KB:
        return None, f"File size must be {MIN_KB}-{MAX_KB} KB."
    if not MIN_STAFF <= staff_size <= MAX_STAFF:
        return None, f"Staff size must be {MIN_STAFF}-{MAX_STAFF}."
    if lilypond not in LILYPOND_VERSIONS:
        return None, "Choose a LilyPond version."
    if not MIN_PAGES_PDF <= pages_pdf <= MAX_PAGES_PDF:
        return None, f"Pages per PDF must be {MIN_PAGES_PDF}-{MAX_PAGES_PDF:,}."
    if not MIN_SYSTEMS <= systems <= MAX_SYSTEMS:
        return None, f"Systems per page must be {MIN_SYSTEMS}-{MAX_SYSTEMS}."
    if not MIN_SYSTEMS <= first_systems <= MAX_SYSTEMS:
        return None, f"Systems on the first page must be {MIN_SYSTEMS}-{MAX_SYSTEMS}."
    # LilyPond font names are case-sensitive: use the installed spelling ("Cadence" -> "cadence")
    installed = {f.lower(): f for f in ((_lp_info or {}).get("music_fonts") or [])}
    music_font = installed.get(music_font.lower(), music_font)
    if music_font.lower() in OUTLINE_REQUIRED:
        outline_fonts = True          # required for this font; can't be switched off
    for label, name in (("Text font", text_font), ("Music font", music_font)):
        if len(name) > 100 or any(ch in name for ch in '"\\\n'):
            return None, f"{label}: please use a plain font name (no quotes or backslashes)."
    for name, r in (("Starting", range_start), ("Ending", range_end)):
        if r is not None and (len(r) != length or any(t not in notes for t in r)):
            return None, f"{name} permutation must be {length} of the ticked notes."
        if r is not None and not perm_allowed(r, repeat_mode):
            return None, f"{name} permutation repeats a note, which this setting doesn't allow."
    if range_start and range_end:
        idx = lambda r: rank([notes.index(t) for t in r], len(notes), length, repeat_mode)
        if idx(range_end) <= idx(range_start):
            return None, "Permutation not possible: the ending must come after the starting permutation."
    return {"length": length, "notes": notes, "max_kb": max_kb,
            "range_start": list(range_start) if range_start else None,
            "range_end": list(range_end) if range_end else None,
            "spelling": spelling, "enharmonics": enharmonics, "save_to": save_to,
            "write_txt": write_txt, "staff_size": staff_size,
            "systems_per_page": systems, "first_page_systems": first_systems, "text_font": text_font, "music_font": music_font,
            "pages_per_pdf": pages_pdf,
            "lilypond": lilypond,
            "clef": clef, "pitch": pitch, "placement": placement,
            "no_repeat_acc": no_repeat_acc, "repeat_mode": repeat_mode,
            "pdf_links": pdf_links, "outline_fonts": outline_fonts,
            "chunk_labels": chunk_labels}, None


PDF_LINKS = {"off": "No links", "notes": "Links on notes", "all": "All links"}
# Title-block text widths (measured with LilyPond 2.26 at staff size 20; they scale with
# the staff size). Text wider than TEXT_LINE_PT is broken into centred lines.
DASH = "\\char ##x2013 "        # the en dash that starts a title / subtitle suffix
TEXT_LINE_PT = 480            # the music line is about 516 pt wide on letter paper
TITLE_PT_PER_CHAR = 10.0
SUBTITLE_PT_PER_CHAR = 5.9
PIECE_PT_PER_NOTE = 15.0      # the range line, per note name
SUBTITLE_LEADING = 2.8        # baseline to baseline of a subtitle on several lines (LilyPond's usual: 3)
SUBTITLE_GAP_EXTRA_PT = 6     # extra space between the subtitle and the range line
# added to the end of the title / subtitle on every score (LilyPond markup; the files
# are plain ASCII, so the en dash is written as its character code)
TITLE_SUFFIX = {"norepeat": '\\char ##x2013 "Excluding Repeated Notes"',
                "once": '\\char ##x2013 "Using Each Note Once"'}
SUBTITLE_SUFFIX = {"nearest": '\\char ##x2013 "nearest within a 4th"',
                   "fixed": '\\char ##x2013 "same octave"'}
REPEAT_MODES = {"all": "Repeats allowed",
                "norepeat": "Exclude repeated notes",     # no note twice in a row
                "once": "Use each note once"}             # no note repeated anywhere


def perm_count(n, k, mode):
    """How many permutations of k notes chosen from n, in a given mode."""
    if mode == "once":
        return math.perm(n, k) if k <= n else 0
    if mode == "norepeat":
        return n * (n - 1) ** (k - 1)   # 0 when only one note is ticked
    return n ** k


def tail_count(n, k, j, mode):
    """How many ways to finish a permutation once its first j notes are chosen."""
    if mode == "once":
        return math.perm(n - j, k - j)
    if mode == "norepeat":
        return (n - 1) ** (k - j)
    return n ** (k - j)


def unrank(i, n, k, mode):
    """The i-th permutation (alphabetical order of note positions), as positions."""
    out, prev, avail = [], None, list(range(n))
    for pos in range(k):
        r, i = divmod(i, tail_count(n, k, pos + 1, mode))
        if mode == "once":
            d = avail.pop(r)
        elif mode == "norepeat":
            d = r if prev is None or r < prev else r + 1   # skip the previous note
        else:
            d = r
        out.append(d)
        prev = d
    return out


def rank(digits, n, k, mode):
    """Position of a permutation (given as note positions) in alphabetical order."""
    i, prev, avail = 0, None, list(range(n))
    for pos, d in enumerate(digits):
        if mode == "once":
            r = avail.index(d)
            avail.remove(d)
        elif mode == "norepeat":
            r = d if prev is None or d < prev else d - 1
        else:
            r = d
        i += r * tail_count(n, k, pos + 1, mode)
        prev = d
    return i


def perm_allowed(tokens, mode):
    if mode == "once":
        return len(set(tokens)) == len(tokens)
    if mode == "norepeat":
        return all(a != b for a, b in zip(tokens, tokens[1:]))
    return True


def bars_per_system(length):
    """2 notes: 6 measures per system; 3-4: 4; 5-6: 2; 7 or more: 1."""
    if length <= 2:
        return 6
    if length <= 4:
        return 4
    if length <= 6:
        return 2
    return 1


class Plan:
    """Everything derived from one set of settings."""

    PITCH_TAG = {"c,": "c2", "c": "c3", "c'": "c4", "c''": "c5", "c'''": "c6"}  # for folder names

    def __init__(self, settings):
        self.notes = list(settings["notes"])
        self.length = settings["length"]
        self.max_bytes = settings["max_kb"] * KB
        self.clef = settings.get("clef", "treble")
        self.pitch = settings.get("pitch", "c'")
        self.placement = settings.get("placement", "fixed")
        self.no_repeat_acc = bool(settings.get("no_repeat_acc", False))
        # labels such as "A B x x" above the staff where a new block of the list begins
        self.chunk_labels = bool(settings.get("chunk_labels", True))
        self.staff_size = int(settings.get("staff_size", 20))
        self.systems_per_page = int(settings.get("systems_per_page", 12))
        # the first page of every PDF also holds the title block, so it can have fewer
        # systems (runs saved by older versions: same count on every page)
        self.first_page_systems = int(settings.get("first_page_systems", self.systems_per_page))
        self.bars_per_system = bars_per_system(self.length)   # measures per line
        self.text_font = settings.get("text_font") or ""
        self.music_font = settings.get("music_font") or ""
        self.outline_fonts = (bool(settings.get("outline_fonts"))
                              or self.music_font.lower() in OUTLINE_REQUIRED)
        self.lilypond = settings.get("lilypond", "2.26")
        self.version = "2.26.0" if self.lilypond == "2.26" else "2.24.0"
        # Page breaks are placed by this program (fast, low-memory page layout),
        # and each \score holds whole pages, about SCORE_TARGET measures.
        # From SPLIT_FROM notes each permutation is split evenly over two lines
        # (no barline at the split), so a page holds half as many measures.
        self.split_at = (self.length + 1) // 2 if self.length >= SPLIT_FROM else 0
        per_page = lambda systems: (max(1, systems // 2) if self.split_at
                                    else systems * self.bars_per_system)
        self.measures_per_page = per_page(self.systems_per_page)        # pages after the first
        self.first_page_measures = per_page(self.first_page_systems)    # each PDF's first page
        # Each PDF is a LilyPond \\book of pages_per_pdf pages. Inside it the music is in
        # \\score blocks of whole pages (about SCORE_TARGET measures) that divide the
        # book exactly, so books always end on a block boundary.
        self.pages_per_pdf = int(settings.get("pages_per_pdf", 100))
        target = max(1, round(SCORE_TARGET / self.measures_per_page))
        block_pages = max(d for d in range(1, min(target, self.pages_per_pdf) + 1)
                          if self.pages_per_pdf % d == 0)
        # a book's first \score block starts with its (shorter or longer) first page
        self.score_measures = self.measures_per_page * block_pages
        self.first_score_measures = self.first_page_measures + self.measures_per_page * (block_pages - 1)
        self.book_measures = self.first_page_measures + self.measures_per_page * (self.pages_per_pdf - 1)
        self.piece_room = 48 * self.length + 48   # space reserved for "to <last>"
        # space reserved for each book's  \\bookOutputName "first-last"
        self.book_room = 2 * self.length * max(len(n) for n in settings["notes"]) + 24
        self.base = len(self.notes)
        self.mode = settings.get("repeat_mode", "all")
        self.pdf_links = settings.get("pdf_links", "off")
        self.total = perm_count(self.base, self.length, self.mode)   # size of the full set
        # Optional range: first and last permutation to write (inclusive).
        rs, re_ = settings.get("range_start"), settings.get("range_end")
        self.first = self.index_of(rs) if rs else 0
        self.last = self.index_of(re_) if re_ else self.total - 1
        self.count = self.last - self.first + 1
        self.partial = self.count != self.total
        self.depth = min(CHUNK_DEPTH, self.length - 1)
        self.chunk_size = tail_count(self.base, self.length, self.depth, self.mode)
        self.out_dir = os.path.join(settings.get("save_to") or DATA_DIR,
                                    settings.get("folder_name") or self.folder_name(settings, compact=False))
        self.working = os.path.join(self.out_dir, "_in_progress.ly")
        self.write_txt = bool(settings.get("write_txt", False))
        self.txt_working = os.path.join(self.out_dir, "_in_progress.txt")
        self.index_path = os.path.join(self.out_dir, "index.csv")
        # File names are "first-last". When that would make paths too long for Windows,
        # the last permutation is shortened to its final notes ("tail"), like a page range
        # 1234-56, and files also close wherever the notes before the tail change, so the
        # tail always identifies the last permutation. Kept in the settings for resuming.
        self.name_tail = settings.get("name_tail") or self.fitting_tail(settings["notes"])

    def folder_name(self, settings, compact=True):
        """The run folder's name, from the settings. compact (new runs): all 12 notes are
        written "chromatic", and a range whose numbers are very long is written as its
        first number and a count. Runs started by older versions keep their old names."""
        notes = "".join(self.notes)
        if compact and len(self.notes) == 12 and not settings.get("enharmonics"):
            notes = "chromatic" + ("-flats" if settings.get("spelling") == "flats" else "")
        rng = ""
        if self.partial:
            rng = f"-from-{self.first + 1}-to-{self.last + 1}"
            if compact and len(str(self.last + 1)) > 9:
                rng = f"-from-{self.first + 1}-count-{self.count}"
        return (f"len{self.length}-{notes}-{self.clef}-{self.PITCH_TAG[self.pitch]}"
                + {"norepeat": "-norepeat", "once": "-once"}.get(self.mode, "")
                + ("-nearest" if self.placement == "nearest" else "")
                + (f"-staff{self.staff_size}" if self.staff_size != 20 else "") + rng)

    def fitting_tail(self, notes):
        """How many final notes of the last permutation fit in file names (all of them if
        the full name fits; 0 if even one doesn't)."""
        if os.name != "nt":
            return self.length
        widest = max(len(n) for n in notes)
        fixed = len(os.path.abspath(self.out_dir)) + 1 + self.length * widest + 1 + 4  # dir\first-....pdf
        room = WINDOWS_PATH_LIMIT - fixed
        return max(0, min(self.length, room // widest))

    @property
    def short_names(self):
        return self.name_tail < self.length

    def range_name(self, first, last):
        """File name for permutations first..last: 'first-last', or 'first-tail' when shortened."""
        tail = self.tokens_at(last)[self.length - self.name_tail:]
        return self.name_at(first) + "-" + "".join(tail)

    def tail_boundary(self, i):
        """True if permutation i starts a new block of the notes before the tail (shortened
        names only): files and text lists then close before i."""
        if not self.short_names or i <= self.first:
            return False
        keep = self.length - self.name_tail
        return self.tokens_at(i)[:keep] != self.tokens_at(i - 1)[:keep]

    def book_pages(self, measures):
        """Pages used by the first `measures` measures of one book (PDF)."""
        if measures <= 0:
            return 0
        rest = measures - self.first_page_measures
        return 1 + (-(-rest // self.measures_per_page) if rest > 0 else 0)

    def file_pages(self, measures):
        """Pages used by a score file of `measures` measures (whole books, then the rest)."""
        full, rest = divmod(measures, self.book_measures)
        return full * self.pages_per_pdf + self.book_pages(rest)

    def page_ends_after(self, bar_in_book):
        """True if measure number bar_in_book (1 = the book's first) ends a page."""
        if bar_in_book <= self.first_page_measures:
            return bar_in_book == self.first_page_measures
        return (bar_in_book - self.first_page_measures) % self.measures_per_page == 0

    def index_of(self, tokens):
        if self.mode != "all":
            return rank([self.notes.index(t) for t in tokens], self.base, self.length, self.mode)
        i = 0
        for t in tokens:
            i = i * self.base + self.notes.index(t)
        return i

    def tokens_at(self, i):
        if self.mode != "all":
            return [self.notes[d] for d in unrank(i, self.base, self.length, self.mode)]
        parts = []
        for _ in range(self.length):
            i, r = divmod(i, self.base)
            parts.append(self.notes[r])
        return parts[::-1]

    def line_at(self, i):
        return " ".join(self.tokens_at(i))

    def name_at(self, i):
        """File-name form: the notes run together, e.g. 'aaisbc' (dashes separate parts)."""
        return "".join(self.tokens_at(i))

    def chunk_label(self, i):
        if i > self.last:
            return "done"
        return " ".join(self.tokens_at(i)[:self.depth] + ["x"] * (self.length - self.depth))

    # ---- LilyPond pieces ----
    # ---- printed names: upper case, with real sharp / flat glyphs ----
    @staticmethod
    def mk_note(tok, after=""):
        """'ais' -> A + sharp glyph, 'bes' -> B + flat glyph, 'c' -> C."""
        letter, rest = tok[0].upper(), tok[1:]
        glyph = " \\noteSharp" if rest == "is" else " \\noteFlat" if rest in ("es", "s") else ""
        tail = f' "{after}"' if after else ""
        if not glyph and not tail:
            return f'"{letter}"'
        return f'\\concat {{ "{letter}"{glyph}{tail} }}'

    def mk_perm(self, tokens):
        return "\\line { " + " ".join(
            self.mk_note(t) if t != "x" else "\\anyNote" for t in tokens) + " }"

    def fonts_block(self):
        """Text and/or music font, in the syntax of the chosen LilyPond version."""
        if not (self.text_font or self.music_font):
            return ""
        if self.lilypond == "2.26":
            lines = []
            if self.music_font:
                lines += [f"  % {MUSIC_FONT_WARNING}",
                          f'  property-defaults.fonts.music = "{self.music_font}"']
            if self.text_font:
                lines += [f'  property-defaults.fonts.serif = "{self.text_font}"']
            return "\n".join(lines) + "\n"
        # LilyPond 2.24: one set-global-fonts call sets text and music fonts together
        lines = ["  #(define fonts", "     (set-global-fonts"]
        if self.music_font:
            lines += [f"       #:music \"{self.music_font}\"   ; {MUSIC_FONT_WARNING}",
                      f"       #:brace \"{self.music_font}\""]
        if self.text_font:
            lines += [f"       #:roman \"{self.text_font}\""]
        lines += ["       #:factor (/ staff-height pt 20)))"]
        return "\n".join(lines) + "\n"

    def spacing_block(self):
        # LilyPond measures these gaps in staff spaces; a staff space is staff-size/4 pt
        ss = self.staff_size / 4.0
        g = lambda pt: f"{pt / ss:.2f}".rstrip("0").rstrip(".")
        return (
            "  % values are in staff spaces; each is LilyPond's usual gap plus extra room\n"
            f"  % page header -> top system: usual (6 and 1) plus {PAGE_EXTRA_PT} pt\n"
            f"  top-system-spacing.basic-distance = #{g(6 * ss + PAGE_EXTRA_PT)}\n"
            f"  top-system-spacing.padding = #{g(1 * ss + PAGE_EXTRA_PT)}\n"
            f"  % bottom system -> footer: usual (1 and 1) plus {PAGE_EXTRA_PT} pt\n"
            f"  last-bottom-spacing.basic-distance = #{g(1 * ss + PAGE_EXTRA_PT)}\n"
            f"  last-bottom-spacing.padding = #{g(1 * ss + PAGE_EXTRA_PT)}\n"
            f"  % first page: LilyPond's usual gap under the titles (5 and 0.5) plus {FIRST_PAGE_EXTRA_PT} pt\n"
            f"  markup-system-spacing.basic-distance = #{g(5 * ss + FIRST_PAGE_EXTRA_PT)}\n"
            f"  markup-system-spacing.padding = #{g(0.5 * ss + FIRST_PAGE_EXTRA_PT)}\n"
            f"  % subtitle -> range line (\"A A A A to ...\"): LilyPond's usual gap (1 and 0.5) plus {SUBTITLE_GAP_EXTRA_PT} pt\n"
            f"  markup-markup-spacing.basic-distance = #{g(1 * ss + SUBTITLE_GAP_EXTRA_PT)}\n"
            f"  markup-markup-spacing.padding = #{g(0.5 * ss + SUBTITLE_GAP_EXTRA_PT)}\n"
        )

    def ly_file_header(self):
        """Everything at the top of a file, then the opening of its first \\score."""
        notes = [self.mk_note(n, "," if k < len(self.notes) - 1 else "")
                 for k, n in enumerate(self.notes)]
        spacing = "#1/8" if self.lilypond == "2.26" else "#(ly:make-moment 1/8)"
        return (
            f'\\version "{self.version}"\n'
            + (OUTLINE_SNIPPET.replace("@FONT@", self.music_font or "emmentaler")
               if self.outline_fonts else "")
            + f"#(set-global-staff-size {self.staff_size})\n"
            + {"off": "\\pointAndClickOff   % PDF without point-and-click links (smaller PDFs)\n",
               "notes": "\\pointAndClickOn\n\\pointAndClickTypes #'note-event   % PDF links on notes only:\n"
                        "% clicking a note opens its line in this .ly file\n",
               "all": "\\pointAndClickOn   % PDF with point-and-click links on everything\n"}[self.pdf_links]
            + "\n"
            "% CC0 80x15 badge: vector EPS kept next to this file\n"
            f'ccZeroIcon = \\markup {{ \\epsfile #Y #{BADGE_HEIGHT} "{CC0_EPS_NAME}" }}\n'
            "% sharp / flat glyphs used in titles and labels (size and height adjustable)\n"
            "noteSharp = \\markup { \\raise #0.6 \\fontsize #-3 \\sharp }\n"
            "noteFlat = \\markup { \\raise #0.3 \\fontsize #-3 \\flat }\n"
            "% centred multiplication-style cross standing for \"any note\" in range labels,\n"
            "% drawn from two lines so it never depends on the text font (size and height adjustable)\n"
            "anyNote = \\markup {\n"
            "  \\raise #0.25\n"
            "  \\override #'(thickness . 1.4)\n"
            "  \\combine\n"
            "    \\draw-line #'(0.7 . 0.7)\n"
            "    \\raise #0.7 \\draw-line #'(0.7 . -0.7)\n"
            "}\n\n"
            + PERM_BAR_NUMBER
            + "\\paper {\n"
            "  paper-width = 8.5\\in\n"
            "  paper-height = 11\\in\n"
            f"  max-systems-per-page = {max(self.systems_per_page, self.first_page_systems)}\n"
            "  % page breaks are written into the music, so the quick, low-memory\n"
            "  % page layout is enough even for thousands of pages\n"
            "  page-breaking = #ly:minimal-breaking\n"
            "  indent = 0\\mm   % first line of music starts at the margin too\n"
            + self.spacing_block() +
            "  % the range line under the titles, centred on the page\n"
            "  scoreTitleMarkup = \\markup { \\fill-line { \\fromproperty #'header:piece } }\n"
            "  oddFooterMarkup = \\markup { \\fill-line { \\fromproperty #'header:copyright } }\n"
            "  evenFooterMarkup = \\markup { \\fill-line { \\fromproperty #'header:copyright } }\n"
            + self.fonts_block() +
            "}\n\n"
            "\\layout {\n"
            "  \\context {\n"
            "    \\Score\n"
            f"    proportionalNotationDuration = {spacing}\n"
            "    \\override SpacingSpanner.uniform-stretching = ##t\n"
            '    measureBarType = "."   % thick barline after every measure\n'
            "    barNumberVisibility = #all-bar-numbers-visible\n"
            "    \\override BarNumber.break-visibility = ##(#f #t #t)\n"
            "    % centred on its barline; a very wide number (a billion or more) at the start of a\n"
            "    % line begins at the margin instead, so it never hangs off the left edge\n"
            "    \\override BarNumber.self-alignment-X =\n"
            "      #(lambda (grob)\n"
            "         (let ((st (ly:grob-property grob 'stencil)))\n"
            "           (if (and (eqv? (ly:item-break-dir grob) RIGHT) (ly:stencil? st)\n"
            "                    (> (interval-length (ly:stencil-extent st X)) 8))\n"
            "               LEFT CENTER)))\n"
            "    \\override BarNumber.font-shape = #'italic\n"
            f"    \\override BarNumber.font-size = #{BAR_NUMBER_FONT_SIZE}   % 9 pt at staff size 20\n"
            "    % new lines only where the file says \\break, so every system\n"
            "    % holds exactly the same number of measures\n"
            "    \\override NonMusicalPaperColumn.line-break-permission = ##f\n"
            "    % measure number = the permutation's number (see permBarNumber above)\n"
            "    barNumberFormatter = #(permBarNumber 1)\n"
            "  }\n"
            "  \\context {\n"
            "    \\Voice\n"
            "    \\omit Stem\n"
            "  }\n"
            "  \\context {\n"
            "    \\Staff\n"
            "    \\omit TimeSignature\n"
            "    % dodecaphonic style (set in the music): every note shows its natural, sharp\n"
            "    % or flat, and every accidental gets the same slot so all measures match\n"
            "    % every slot as wide as the widest sign (sharp, flat or natural) in the music font\n"
            "    \\override Accidental.X-extent =\n"
            "      #(lambda (grob)\n"
            "         (let* ((font (ly:grob-default-font grob))\n"
            "                (widths (map (lambda (g)\n"
            "                               (interval-length (ly:stencil-extent (ly:font-get-glyph font g) X)))\n"
            "                             '(\"accidentals.sharp\" \"accidentals.flat\" \"accidentals.natural\"))))\n"
            "           (cons 0 (apply max widths))))\n"
            "    \\override Accidental.horizontal-skylines = #ly:grob::simple-horizontal-skylines-from-extents\n"
            "  }\n"
            "}\n\n"
            "\\header {\n"
            + "  title = \\markup " + self.fit_lines(
                [('"Note Permutations"', 17)]
                + ([(TITLE_SUFFIX[self.mode], 2 + len(TITLE_SUFFIX[self.mode].split('"')[1]))]
                   if self.mode in TITLE_SUFFIX else []), TITLE_PT_PER_CHAR) + "\n"
            + "  subtitle = \\markup " + self.fit_lines(
                [(f'"{self.length}-note permutations of"', len(f"{self.length}-note permutations of")),
                 (" ".join(notes), sum(len(n) > 1 and 4 or 3 for n in self.notes)),
                 (SUBTITLE_SUFFIX.get(self.placement, ""),
                  2 + len(SUBTITLE_SUFFIX.get(self.placement, '""').split('"')[1]))],
                SUBTITLE_PT_PER_CHAR, SUBTITLE_LEADING) + "\n"
            "  copyright = \\markup \\fill-line {\n"
            "    \\line {\n"
            "      \\vcenter \\ccZeroIcon\n"
            "      \\hspace #1\n"
            f'      \\vcenter "{COPYRIGHT_TEXT}"\n'
            "      \\hspace #1\n"
            f'      \\vcenter \\with-url #"{CC0_DEED}" \\fontsize #-2 "{CC0_DEED[8:]}"\n'
            "    }\n"
            "  }\n"
            "  tagline = ##f\n"
            "}\n\n"
        )

    def book_open(self, start_page):
        """Start a \\book: one PDF. Its \\bookOutputName (the range it holds) is written
        into a reserved blank space once the book is finished.
        Returns (text, offset of that space within text)."""
        head = (f"% ---- one PDF: up to {self.pages_per_pdf:,} pages ----\n"
                "\\book {\n  ")
        text = (head + " " * self.book_room + "\n"
                f"  \\paper {{ first-page-number = {start_page} }}\n")
        return text, len(head)

    def book_name(self, first, last):
        return f'\\bookOutputName "{self.range_name(first, last)}"'.ljust(self.book_room)

    def ly_score_open(self, first_index):
        """Start a \\score block (the music is split into blocks of whole pages)."""
        return (
            "\\score {\n"
            + (f"  \\fixed {self.pitch} {{\n" if self.placement == "fixed" else
               "  {  % absolute pitches: each bar starts in the chosen octave, then every\n"
               "     % note takes the octave nearest the previous note (within a fourth)\n")
            + f"    \\clef {self.clef}\n"
            "    \\accidentalStyle dodecaphonic   % a natural, sharp or flat on every note\n"
            f"    \\time {self.length}/4\n"
            # measure N = permutation N of the full set, also in ranged runs
            # LilyPond's own counter only reaches about 2.1 billion, so it counts 1, 2, 3 ...
            # within each block and permBarNumber adds the block's first permutation number
            f"    \\set Score.barNumberFormatter = #(permBarNumber {first_index + 1})\n"
            "    \\set Score.currentBarNumber = #1\n"
            '    \\bar ""\n'
        )

    def fit_lines(self, parts, pt_per_char, leading=None):
        """Markup for title-block text: one centred line if it fits across the page,
        otherwise several centred lines, broken only between the given parts.
        parts: [(markup, width in characters)]; widths are estimates at staff size 20."""
        limit = TEXT_LINE_PT * 20 / self.staff_size / pt_per_char      # characters per line
        lines, cur, used = [], [], 0
        for markup, chars in parts:
            if cur and used + 1 + chars > limit:
                lines.append(cur)
                cur, used = [], 0
            if not cur and markup.startswith(DASH):
                markup = markup[len(DASH):]        # a suffix starting its own line needs no dash
            cur.append(markup)
            used += chars + (1 if used else 0)
        lines.append(cur)
        if len(lines) == 1:
            return "\\line { " + " ".join(lines[0]) + " }"
        column = "\\center-column { " + " ".join("\\line { " + " ".join(l) + " }" for l in lines) + " }"
        if leading:   # distance between the lines' baselines, in staff spaces
            column = f"\\override #'(baseline-skip . {leading}) {column}"
        return column

    def piece_head(self, first):
        """The range line under the titles ("A A A A to D C B A"), centred on the page.
        A long range (wide notes, big staff) goes on two centred lines: the first
        permutation and "to", then the last one."""
        first_perm = self.mk_perm(self.tokens_at(first))
        # width in points: about 15 pt per note name at staff size 20
        width = (2 * self.length + 1) * PIECE_PT_PER_NOTE * self.staff_size / 20
        if width > TEXT_LINE_PT:
            return f'  \\header {{\n    piece = \\markup \\center-column {{ \\line {{ {first_perm} "to" }} '
        return f'  \\header {{\n    piece = \\markup \\line {{ {first_perm} "to" '

    def ly_score_close(self, first=None, last=None, placeholder=False):
        """End a \\score block. The first block of each file carries the file's
        range ("A A A to ..."); its end is filled in when the file is finished,
        so a placeholder of spaces is written if the end isn't known yet.
        Returns (text, offset of the placeholder within text or None)."""
        text, offset = "  }\n", None
        if first is not None:
            head = self.piece_head(first)
            if placeholder:
                offset = len(text) + len(head)
                text += head + " " * self.piece_room + " }\n  }\n"
            else:
                text += head + self.mk_perm(self.tokens_at(last)) + " }\n  }\n"
        return text + "}\n\n", offset

    def whole_file(self, first, last, first_page=1, out_name=None):
        """A complete score file holding permutations first..last in one book."""
        btext, boff = self.book_open(first_page)
        name = out_name or self.range_name(first, last)
        btext = (btext[:boff] + f'\\bookOutputName "{name}"'.ljust(self.book_room)
                 + btext[boff + self.book_room:])
        parts, n = [self.ly_file_header(), btext, self.ly_score_open(first)], 0
        for i in range(first, last + 1):
            if i == first or i % self.chunk_size == 0:
                parts.append(self.ly_chunk_mark(i))
            n += 1
            parts.append(self.ly_bar(i, n))
        close, _ = self.ly_score_close(first, last)
        parts.append(self.ly_padding(n) + close + "}\n")
        return "".join(parts)

    def ly_chunk_mark(self, i):
        label = self.chunk_label(i)
        toks = self.tokens_at(i)[:self.depth] + ["x"] * (self.length - self.depth)
        if not self.chunk_labels:            # turned off: a comment only, nothing printed
            return f'\n    % chunk: {label}\n'
        return f'\n    % chunk: {label}\n    \\mark \\markup \\small {self.mk_perm(toks)}\n'

    def octave_shift(self, tok):
        # The octave runs from the A below the chosen C up to the G-sharp above it
        # (a, ais/bes, b, c, ... gis), so with c' an A is the third below middle C.
        # In LilyPond's own octaves A and B sit above C, so A- and B-letter notes
        # (a, ais, aes, b, bes, bis) go down one octave.
        return -1 if tok[0] in "ab" else 0

    def nearest_octaves(self, tokens):
        """First note in the chosen octave; each next note in whichever octave puts
        it within a fourth of the previous one (counted by letter name, like
        LilyPond's \\relative). Returns absolute LilyPond pitches."""
        out, pos = [], None
        for t in tokens:
            step = LETTER_STEP[t[0]]
            if pos is None:
                pos = (OCTAVE_NUMBER[self.pitch] + self.octave_shift(t)) * 7 + step
            else:
                up = (step - pos % 7) % 7          # letter steps upward, 0-6
                pos += up if up <= 3 else up - 7   # a fourth or less, up or down
            octave = pos // 7
            out.append(t + ("'" * (octave - 3) if octave >= 3 else "," * (3 - octave)))
        return out

    def ly_bar(self, i, bar_in_book):
        notes = self.tokens_at(i)
        if self.placement == "nearest":
            notes = self.nearest_octaves(notes)
        else:   # inside the fixed-octave block, one ' lifts a note an octave higher
            notes = [t + "," * -self.octave_shift(t) for t in notes]
        words = [notes[0] + NOTE_LENGTH] + notes[1:]
        if self.no_repeat_acc:
            # a note that directly repeats the previous one (same pitch and octave) keeps
            # its accidental's slot but doesn't show it, so the spacing stays identical
            for k in range(1, len(notes)):
                if notes[k] == notes[k - 1]:
                    words[k] = "\\tweak Accidental.transparent ##t " + words[k]
        if self.split_at:
            words.insert(self.split_at, '\\bar "" \\break')   # split line, no barline
        line = "    " + " ".join(words) + " |"
        if self.page_ends_after(bar_in_book):
            line += " \\pageBreak"        # a full page: new page (and new line)
        elif bar_in_book % self.bars_per_system == 0:
            line += " \\break"
        return line + "\n"

    def ly_padding(self, bars_in_file):
        """If the last line of music is short, finish it with invisible measures so
        its real measures are exactly as wide as on every other line."""
        missing = -bars_in_file % self.bars_per_system
        if not missing:
            return ""
        p = CLEF_MIDDLE[self.clef]
        lines = ["",
                 "    % invisible measures: keep the last line's measures the same width. They are",
                 "    % hidden (not removed), so their barlines and numbers still take up their usual",
                 "    % room and every measure on this line is spaced exactly like the full lines",
                 "    % (the staff carries on with invisible lines: with no staff at all the",
                 "    % hidden barlines would have no width and the real measures would stretch)",
                 "    \\stopStaff",
                 "    \\override Staff.StaffSymbol.transparent = ##t",
                 "    \\startStaff",
                 "    \\hideNotes \\hide Score.BarNumber"]
        for k in range(missing):
            notes = [p + NOTE_LENGTH] + [p] * (self.length - 1)
            if k == 0:
                notes.insert(1, "\\hide Staff.BarLine")
            lines.append("    \\absolute { " + " ".join(notes) + " } |")
        return "\n".join(lines) + "\n"

    def write_master(self, files):
        """master.ly: pulls every finished file of this run into one PDF."""
        lines = [
            f'\\version "{self.version}"',
            "% Engraves every file of this run in ONE LilyPond run (the PDFs are split",
            "% into books of the chosen page count). Fine for small runs; for large",
            "% runs use engrave_all.bat (Windows) or engrave_all.command (Mac), which",
            "% engrave one file at a time so LilyPond's memory never fills up.",
            "% Engrave with:  lilypond master.ly   (run it inside this folder,",
            f"% so {CC0_EPS_NAME} - the footer icon - is found)",
            "",
        ] + [f'\\include "{name}"' for name in files]
        tmp = os.path.join(self.out_dir, "master.ly.tmp")
        with open(tmp, "w") as f:
            f.write("\n".join(lines) + "\n")
        os.replace(tmp, os.path.join(self.out_dir, "master.ly"))


ENGRAVE_BAT = r"""@echo off
setlocal
rem ---------------------------------------------------------------------------
rem  Engraves every score file in this folder, ONE LilyPond run per file, so
rem  LilyPond only ever holds one file in memory. Each file makes its own PDFs
rem  (split by the app into books of the chosen page count). Double-click to run.
rem
rem  If LilyPond is not found, put the full path to lilypond.exe here, e.g.
rem    set "LILYPOND=C:\Program Files\lilypond-2.26.0\bin\lilypond.exe"
rem ---------------------------------------------------------------------------
set "LILYPOND=lilypond"
cd /d "%~dp0"

where "%LILYPOND%" >nul 2>nul
if errorlevel 1 (
  for /d %%D in ("%ProgramFiles%\lilypond-*" "%ProgramFiles(x86)%\lilypond-*" "%USERPROFILE%\lilypond-*") do (
    if exist "%%~D\bin\lilypond.exe" set "LILYPOND=%%~D\bin\lilypond.exe"
  )
)

set /a DONE=0, FAILED=0
for %%F in (*.ly) do call :engrave "%%~F"
echo.
echo Finished: %DONE% file(s) engraved, %FAILED% with errors.
pause
exit /b

:engrave
if /i "%~1"=="master.ly" exit /b
if /i "%~1"=="_in_progress.ly" exit /b
echo.
echo === Engraving %~1 ...
"%LILYPOND%" "%~1"
if errorlevel 1 (set /a FAILED+=1) else (set /a DONE+=1)
exit /b
"""

ENGRAVE_COMMAND = r"""#!/bin/bash
# ---------------------------------------------------------------------------
#  Engraves every score file in this folder, ONE LilyPond run per file, so
#  LilyPond only ever holds one file in memory. Each file makes its own PDFs
#  (split by the app into books of the chosen page count). Double-click to run.
#
#  If LilyPond is not found, put its full path here, for example:
#    LILYPOND="$HOME/lilypond-2.26.0/bin/lilypond"
#    LILYPOND="/opt/homebrew/bin/lilypond"
# ---------------------------------------------------------------------------
LILYPOND="lilypond"
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/bin:$PATH"
cd "$(dirname "$0")" || exit 1

if ! command -v "$LILYPOND" >/dev/null 2>&1; then
  for c in "$HOME"/lilypond-*/bin/lilypond /Applications/lilypond-*/bin/lilypond \
           /Applications/LilyPond*.app/Contents/Resources/bin/lilypond; do
    [ -x "$c" ] && LILYPOND="$c"
  done
fi

done_n=0; failed=0
for f in *.ly; do
  case "$f" in master.ly|_in_progress.ly) continue ;; esac
  [ -e "$f" ] || continue
  echo
  echo "=== Engraving $f ..."
  if "$LILYPOND" "$f"; then done_n=$((done_n+1)); else failed=$((failed+1)); fi
done
echo
echo "Finished: $done_n file(s) engraved, $failed with errors."
read -r -p "Press Return to close."
"""


def write_engrave_scripts(folder, lilypond=None):
    """engrave_all.bat (Windows) and engrave_all.command (Mac) in a run folder,
    set to use the LilyPond this app found (they still search if it's gone)."""
    bat, cmd = ENGRAVE_BAT, ENGRAVE_COMMAND
    if lilypond and '"' not in lilypond:
        bat = bat.replace('set "LILYPOND=lilypond"', f'set "LILYPOND={lilypond}"')
        cmd = cmd.replace('LILYPOND="lilypond"', f'LILYPOND="{lilypond}"')
    with open(os.path.join(folder, "engrave_all.bat"), "w", newline="\r\n") as f:
        f.write(bat)
    path = os.path.join(folder, "engrave_all.command")
    with open(path, "w", newline="\n") as f:
        f.write(cmd)
    try:
        os.chmod(path, 0o755)   # double-clickable on a Mac
    except OSError:
        pass


def fresh_state(settings):
    return {
        "version": STATE_VERSION,
        "settings": settings,
        "next_index": Plan(settings).first,   # next permutation to write
        "file_first": None,  # name of the first permutation in the current file
        "file_start": None,  # index of the first permutation in the current file
        "file_count": 0,     # bars written to the current file
        "file_bytes": 0,     # bytes written to the current file
        "score_index": 0,    # which \score block of the current file is open
        "score_bars": 0,     # measures in that block so far
        "piece_at": None,    # where the file's range line is filled in at the end
        "book_first": None,  # first permutation in the current \\book (PDF)
        "book_bars": 0,      # measures in that book so far
        "book_name_at": None,  # where its \\bookOutputName is filled in
        "pages_done": 0,     # pages in finished files (page numbers carry on)
        "elapsed": 0.0,      # running time across all runs (pauses excluded)
        "done": False,
        "files": [],         # finished files
    }


class Engine:
    """Does the generating on a background thread; the web page controls it."""

    def __init__(self):
        self.lock = threading.Lock()
        self.wake = threading.Condition(self.lock)
        self.thread = None
        self.paused = False
        self.stop_requested = False
        self.status = "idle"   # idle | running | paused | stopped | done | error
        self.message = "Choose your settings, then press Start."
        self.recent = []       # last few bars written, for the preview
        self.state = self._load()
        self.plan = Plan(self.state["settings"])

    # ---------- persistence ----------
    def _load(self):
        if not os.path.exists(STATE_FILE):
            return fresh_state(dict(DEFAULT_SETTINGS))
        try:
            with open(STATE_FILE) as f:
                st = json.load(f)
        except (OSError, ValueError):
            st = {}
        if st.get("version") != STATE_VERSION:
            self.message = (f"Found a {STATE_FILE} from an earlier version; "
                            "it will be replaced when you press Start.")
            return fresh_state(dict(DEFAULT_SETTINGS))
        if st["done"]:
            self.status = "done"
            self.message = f"Last run finished: {len(st['files'])} file(s)."
        elif st["next_index"] > 0:
            self.status = "stopped"
            self.message = (f"Ready to resume at "
                            f"{Plan(st['settings']).line_at(st['next_index'])}.")
        return st

    def _save(self):
        if getattr(self, "_txt", None):
            self._txt.flush()   # never record more text than is really on disk
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.state, f, indent=2)
        os.replace(tmp, STATE_FILE)  # atomic: the memory file is never half-written

    def _finish_file(self):
        st, plan = self.state, self.plan
        last = st["next_index"] - 1
        first_block = st["score_index"] == 0 and st.get("piece_at") is None
        close, _ = plan.ly_score_close(st["file_start"] if first_block else None, last)
        with open(plan.working, "ab") as f:
            f.write((plan.ly_padding(st["file_count"]) + close
                     + "}\n").encode("ascii"))   # end of the file's last \\book
        if st.get("piece_at") is not None:
            # fill in the end of the range line in the file's first \score block
            end = (plan.mk_perm(plan.tokens_at(last))).ljust(plan.piece_room)
            with open(plan.working, "r+b") as f:
                f.seek(st["piece_at"])
                f.write(end.encode("ascii"))
        if st.get("book_name_at") is not None:
            self._fill(plan.working, st["book_name_at"],
                       plan.book_name(st["book_first"], last))
            self._index_row(st["book_first"], last, st.get("book_page", 1))
        st["pages_done"] = st.get("pages_done", 0) + plan.file_pages(st["file_count"])
        name = (plan.range_name(st["file_start"], last) if st.get("file_start") is not None
                else f"{st['file_first']}-{plan.name_at(last)}") + ".ly"
        os.replace(plan.working, os.path.join(plan.out_dir, name))
        st["files"].append(name)
        st.update(file_first=None, file_start=None, file_count=0, file_bytes=0,
                  score_index=0, score_bars=0, piece_at=None,
                  book_first=None, book_bars=0, book_name_at=None)
        plan.write_master(st["files"])
        self._save()

    def _index_row(self, first, last, first_page):
        """Add one PDF to index.csv: its name, range, measures and pages."""
        st, plan = self.state, self.plan
        rows = ""
        if not st.get("index_bytes"):
            rows = "pdf,first permutation,last permutation,first measure,last measure,first page,last page\n"
        pages = plan.book_pages(last - first + 1)
        rows += (f"{plan.range_name(first, last)}.pdf,{plan.line_at(first)},"
                 f"{plan.line_at(last)},{first + 1},{last + 1},{first_page},{first_page + pages - 1}\n")
        data = rows.encode("ascii")
        with open(plan.index_path, "ab") as f:
            f.write(data)
        st["index_bytes"] = st.get("index_bytes", 0) + len(data)

    @staticmethod
    def _fill(path, offset, text):
        """Write text over a reserved blank space earlier in a file."""
        with open(path, "r+b") as f:
            f.seek(offset)
            f.write(text.encode("ascii"))

    # ---------- controls ----------
    def start(self, raw_settings=None):
        with self.lock:
            if self.status == "running":
                return
            if self.status == "paused":
                self.paused = False
                self.status, self.message = "running", ""
                self.wake.notify_all()
                return
            if self.status != "stopped":
                # Fresh run with the panel's settings.
                settings, err = validate(raw_settings or {})
                if err:
                    self.message = err
                    return
                settings["folder_name"] = Plan(settings).folder_name(settings)   # new-style name
                plan = Plan(settings)
                if plan.name_tail < 1:
                    widest = max(len(n) for n in plan.notes)
                    need = len(os.path.abspath(plan.out_dir)) + 1 + plan.length * widest + 2 * widest + 5
                    self.message = (f"Even shortened, file paths would be about {need} characters, past "
                                    "Windows' 260 limit. Choose a save folder with a shorter "
                                    "path (e.g. C:\\Perm).")
                    return
                settings["name_tail"] = plan.name_tail      # resume with the same names
                self.state = fresh_state(settings)
                self.plan = plan
                self.recent = []
            self.paused = self.stop_requested = False
            self.status, self.message = "running", ""
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def pause(self):
        with self.lock:
            if self.status == "running":
                self.paused = True
                self.status, self.message = "paused", "Paused. Press Start to continue."

    def stop(self):
        with self.lock:
            if self.status not in ("running", "paused"):
                return
            self.stop_requested = True
            self.paused = False
            self.wake.notify_all()
            thread = self.thread
        if thread:
            thread.join()

    def reset(self):
        with self.lock:
            if self.status in ("running", "paused"):
                self.message = "Stop first, then Reset."
                return
            for path in (STATE_FILE, self.plan.working):
                if os.path.exists(path):
                    os.remove(path)
            self.state = fresh_state(self.state["settings"])
            self.recent = []
            self.status, self.message = "idle", "Reset. Choose your settings, then press Start."

    def snapshot(self):
        with self.lock:
            st, plan = self.state, self.plan
            i = min(st["next_index"], plan.last + 1)
            done = i - plan.first
            return {
                "status": self.status,
                "message": self.message,
                "locked": self.status in ("running", "paused", "stopped"),
                "settings": st["settings"],
                "note_sets": NOTE_SETS,
                "spellings": SPELLINGS,
                "enharmonics": ENHARMONICS,
                "script_dir": DATA_DIR,
                "default_place": DEFAULT_PLACE,
                "app_window": APP_WINDOW is not None,
                "window_note": WINDOW_NOTE,
                "clefs": CLEFS,
                "pitches": PITCHES,
                "placements": PLACEMENTS,
                "pdf_links": PDF_LINKS,
                "limits": {"min_len": MIN_LEN, "max_len": MAX_LEN,
                           "min_kb": MIN_KB, "max_kb": MAX_KB,
                           "min_staff": MIN_STAFF, "max_staff": MAX_STAFF,
                           "min_systems": MIN_SYSTEMS, "max_systems": MAX_SYSTEMS},
                "music_font_warning": MUSIC_FONT_WARNING,
                "outline_warning": OUTLINE_WARNING,
                "outline_required": sorted(OUTLINE_REQUIRED),
                "lilypond": _lp_info,
                "engrave": engraver.snapshot(),
                "lilypond_versions": LILYPOND_VERSIONS,
                "done_count": done,
                "total": plan.count,
                "done_text": f"{done:,}",
                "total_text": f"{plan.count:,}",
                "percent": 100 * done / plan.count,
                "elapsed": st["elapsed"],
                "chunk": plan.chunk_label(i),
                "out_dir": plan.out_dir,
                "current_file": (f"{st['file_first']}-…" if st["file_first"] else None),
                "files": st["files"][-50:],
                "file_total": len(st["files"]),
                "recent": self.recent,
            }

    # ---------- the work ----------
    def _run(self):
        try:
            self._work()
        except Exception as e:  # show problems in the panel instead of dying silently
            with self.lock:
                self._close_txt()
                self.status, self.message = "error", f"Error: {e}"

    def _work(self):
        st, plan = self.state, self.plan
        os.makedirs(plan.out_dir, exist_ok=True)
        with open(os.path.join(plan.out_dir, CC0_EPS_NAME), "w") as f:
            f.write(CC0_EPS)   # the footer icon the scores refer to
        write_engrave_scripts(plan.out_dir, find_lilypond().get("path"))
        with self.lock:
            # Cut the working file back to the last saved point so nothing
            # written after the last save gets duplicated.
            if os.path.exists(plan.working):
                with open(plan.working, "r+b") as f:
                    f.truncate(st["file_bytes"])
            elif st["file_count"] > 0:
                st.update(file_first=None, file_start=None, file_count=0, file_bytes=0,
                          score_index=0, score_bars=0, piece_at=None,
                  book_first=None, book_bars=0, book_name_at=None)
            # index.csv: cut back to the last saved point too
            st.setdefault("index_bytes", 0)
            if os.path.exists(plan.index_path):
                with open(plan.index_path, "r+b") as f:
                    f.truncate(st["index_bytes"])
            for key, default in (("txt_bytes", 0), ("txt_first", None), ("txt_files", [])):
                st.setdefault(key, default)
            self._txt = None
            if plan.write_txt:
                if os.path.exists(plan.txt_working):
                    with open(plan.txt_working, "r+b") as f:
                        f.truncate(st["txt_bytes"])
                elif st["txt_bytes"] > 0:
                    st.update(txt_first=None, txt_bytes=0)   # it was already renamed
                self._txt = open(plan.txt_working, "ab")
            self._save()
        out = open(plan.working, "ab")
        last_tick = last_save = time.time()

        while True:
            with self.lock:
                if self.paused:
                    out.flush()
                    self._save()
                    while self.paused and not self.stop_requested:
                        self.wake.wait()
                    last_tick = time.time()  # paused time doesn't count
                if self.stop_requested:
                    out.flush()
                    out.close()
                    self._save()
                    self._close_txt()
                    self.status = "stopped"
                    self.message = (f"Stopped and saved. Press Start to resume at "
                                    f"{plan.line_at(st['next_index'])}.")
                    return
                if st["next_index"] > plan.last:
                    break

                i = st["next_index"]
                new_file = st["file_first"] is None
                new_block, piece_rel, book_rel, fill_book = new_file, None, None, None
                if new_file:
                    text = plan.ly_file_header()
                    book_page = st.get("pages_done", 0) + 1
                    btext, boff = plan.book_open(book_page)
                    book_rel = len(text) + boff
                    text += btext + plan.ly_score_open(i)
                elif st["score_bars"] >= (plan.first_score_measures
                                          if st["score_bars"] == st.get("book_bars", 0)
                                          else plan.score_measures):
                    # (a book's first block holds its first page, so its size differs)
                    # close this \score block (whole pages) and open the next one
                    first_block = st["score_index"] == 0
                    text, piece_rel = plan.ly_score_close(
                        st["file_start"] if first_block else None, placeholder=first_block)
                    if st["book_bars"] >= plan.book_measures:
                        # the book (PDF) is full: close it and start the next one
                        text += "}\n\n"
                        fill_book = (st["book_name_at"], st["book_first"], i - 1)
                        book_page = (st.get("pages_done", 0)
                                     + plan.file_pages(st["file_count"]) + 1)
                        btext, boff = plan.book_open(book_page)
                        book_rel = len(text) + boff
                        text += btext
                    text += plan.ly_score_open(i)
                    new_block = True
                else:
                    text = ""
                if new_block or i % plan.chunk_size == 0:
                    text += plan.ly_chunk_mark(i)
                text += plan.ly_bar(i, 1 if book_rel is not None else st.get("book_bars", 0) + 1)
                data = text.encode("ascii")

                if not new_file and (st["file_bytes"] + len(data) + FOOTER_RESERVE
                                     + plan.piece_room > plan.max_bytes or plan.tail_boundary(i)):
                    out.close()
                    self._finish_file()
                    out = open(plan.working, "ab")
                    continue  # rebuild this bar with the new file's header

                if new_file:
                    st["file_first"] = plan.name_at(i)
                    st["file_start"] = i
                if piece_rel is not None:
                    st["piece_at"] = st["file_bytes"] + piece_rel
                if fill_book:
                    out.flush()
                    self._fill(plan.working, fill_book[0],
                               plan.book_name(fill_book[1], fill_book[2]))
                    self._index_row(fill_book[1], fill_book[2], st.get("book_page", 1))
                if book_rel is not None:
                    st["book_name_at"] = st["file_bytes"] + book_rel
                    st["book_first"] = i
                    st["book_bars"] = 0
                    st["book_page"] = book_page
                st["book_bars"] = st.get("book_bars", 0) + 1
                if new_block:
                    st["score_index"] = 0 if new_file else st["score_index"] + 1
                    st["score_bars"] = 0
                st["score_bars"] += 1
                out.write(data)
                if self._txt:
                    line = (plan.line_at(i) + "\n").encode("ascii")
                    if st["txt_bytes"] > 0 and (st["txt_bytes"] + len(line) > plan.max_bytes
                                                or plan.tail_boundary(i)):
                        self._finish_txt(i - 1)
                    if st["txt_first"] is None:
                        st["txt_first"] = plan.name_at(i)
                        st["txt_start"] = i
                    self._txt.write(line)
                    st["txt_bytes"] += len(line)
                st["file_bytes"] += len(data)
                st["file_count"] += 1
                st["next_index"] += 1
                self.recent = (self.recent + [plan.line_at(i)])[-8:]

                now = time.time()
                st["elapsed"] += now - last_tick
                last_tick = now
                if now - last_save > 1.0:
                    out.flush()
                    self._save()
                    last_save = now

            time.sleep(ROW_DELAY)  # 0 still lets the panel get a word in

        with self.lock:
            out.close()
            if st["file_count"] > 0:
                self._finish_file()
            if self._txt and st["txt_bytes"] > 0:
                self._finish_txt(plan.last, reopen=False)
            st["done"] = True
            self._save()
            self._close_txt()
            if os.path.exists(plan.txt_working):
                os.remove(plan.txt_working)   # nothing left in it
            self.status = "done"
            nt = len(st.get("txt_files", []))
            extra = f" and {nt} text file(s)" if plan.write_txt else ""
            self.message = (f"Finished. {len(st['files'])} score file(s){extra} written to "
                            f"'{plan.out_dir}'.")

    def _finish_txt(self, last, reopen=True):
        """Close the current text list, name it first-last.txt, start a new one."""
        st, plan = self.state, self.plan
        self._txt.close()
        name = (plan.range_name(st["txt_start"], last) if st.get("txt_start") is not None
                else f"{st['txt_first']}-{plan.name_at(last)}") + ".txt"
        os.replace(plan.txt_working, os.path.join(plan.out_dir, name))
        st["txt_files"].append(name)
        st.update(txt_first=None, txt_start=None, txt_bytes=0)
        self._txt = open(plan.txt_working, "ab") if reopen else None
        self._save()

    def _close_txt(self):
        if getattr(self, "_txt", None):
            self._txt.close()
        self._txt = None


# ---------------- control panel ----------------
PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Melodarium</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 1024 1024%22%3E%3Crect x=%2232%22 y=%2232%22 width=%22960%22 height=%22960%22 rx=%22190%22 fill=%22%23111111%22/%3E%3Crect x=%2238%22 y=%2238%22 width=%22948%22 height=%22948%22 rx=%22184%22 fill=%22none%22 stroke=%22%23ffffff%22 stroke-opacity=%220.16%22 stroke-width=%2212%22/%3E%3Cg transform=%22translate(30.53 322.16) scale(1.6894)%22%3E%3Cg fill=%22none%22 stroke=%22%23FFFFFF%22 stroke-width=%2213%22 stroke-linecap=%22round%22 stroke-linejoin=%22round%22%3E%3Cpath d=%22M 42 115 C 110 131.75 134 11 203 29 S 297 139.5 363 89 S 450 17 520 65%22/%3E%3Cpath d=%22M 42 115 C 110 141.75 134 43 203 61 S 297 169.5 363 121 S 450 49 520 65%22/%3E%3Cpath d=%22M 42 115 C 110 153.75 134 75 203 93 S 297 199.5 363 153 S 450 81 520 65%22/%3E%3Cpath d=%22M 42 115 C 110 165.75 134 107 203 125 S 297 229.5 363 185 S 450 113 520 65%22/%3E%3C/g%3E%3Cg fill=%22%23FFFFFF%22%3E%3Ccircle cx=%22154.82%22 cy=%2239.6%22 r=%2219%22/%3E%3Ccircle cx=%22297.34%22 cy=%2294.44%22 r=%2219%22/%3E%3Ccircle cx=%22520%22 cy=%2265%22 r=%2219%22/%3E%3C/g%3E%3C/g%3E%3C/svg%3E">
<style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#1d1d1f;--muted:#6b6b70;--line:#e3e1dc;
--accent:#2f6f5e;--accent-ink:#fff;--accent-soft:#e3efe9;--warn:#b7791f;--stop:#b23b3b;--track:#ecebe6}
/* dark: follows the system, unless the logo was clicked to choose light or dark */
:root{color-scheme:light dark}
:root[data-theme=light]{color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#151517;--card:#1f1f22;--ink:#ececee;
--muted:#9a9aa1;--line:#2e2e33;--accent:#5fb39b;--accent-ink:#0f1a17;--accent-soft:#1f3530;
--warn:#e0a84a;--stop:#e07070;--track:#2a2a2e}}
:root[data-theme=dark]{color-scheme:dark;--bg:#151517;--card:#1f1f22;--ink:#ececee;
--muted:#9a9aa1;--line:#2e2e33;--accent:#5fb39b;--accent-ink:#0f1a17;--accent-soft:#1f3530;
--warn:#e0a84a;--stop:#e07070;--track:#2a2a2e}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:720px;margin:0 auto;padding:28px 16px 48px}
h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--muted);margin:0 0 20px;font-size:14px}
.mono{font-family:ui-monospace,Menlo,Consolas,monospace}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:14px}
h2{font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin:0 0 12px}
.field{margin-bottom:18px}
.fhead{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px}
.fhead strong{font-variant-numeric:tabular-nums}
.hint{color:var(--muted);font-size:13px}
input[type=range]{width:100%;accent-color:var(--accent)}
.chips{display:grid;grid-template-columns:repeat(6,1fr);gap:6px}
@media (max-width:480px){.chips{grid-template-columns:repeat(4,1fr)}}
.chip{position:relative}
.chip input{position:absolute;opacity:0;inset:0;margin:0;cursor:pointer}
.chip span{display:block;text-align:center;padding:8px 0;border:1px solid var(--line);border-radius:8px;
font:600 14px ui-monospace,Menlo,Consolas,monospace;user-select:none}
.chip input:checked + span{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
.chip input:focus-visible + span{outline:2px solid var(--accent);outline-offset:2px}
.chip input:disabled{cursor:default}
.chip input:disabled:not(:checked) + span{opacity:.35}
.seg{display:flex;flex-wrap:wrap;gap:6px}
.seg label{position:relative}
.seg input{position:absolute;opacity:0;inset:0;margin:0;cursor:pointer}
.seg span{display:block;padding:8px 14px;border:1px solid var(--line);border-radius:8px;font-weight:600;font-size:14px;user-select:none}
.seg input:checked + span{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
.seg input:focus-visible + span{outline:2px solid var(--accent);outline-offset:2px}
.seg .mono{font-family:ui-monospace,Menlo,Consolas,monospace}
#pitches span{padding:8px 10px}   /* five octave buttons on one line */
.two{display:grid;grid-template-columns:3fr 2fr;gap:18px}
@media (max-width:560px){.two{grid-template-columns:1fr}}
.rangerow{display:flex;gap:10px;align-items:center;margin-bottom:6px}
.rlabel{flex:0 0 42px;align-self:flex-start;padding-top:8px;color:var(--muted);font-size:13px}
.boxes{display:flex;flex-wrap:wrap;gap:4px}
.boxes input{width:44px;text-align:center;font:600 15px ui-monospace,Menlo,Consolas,monospace;padding:7px 2px;
border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink)}
.boxes input:focus{outline:2px solid var(--accent);outline-offset:1px}
.rangerow.bad .boxes input,.boxes input.invalid{border-color:var(--stop);
background:color-mix(in srgb,var(--stop) 14%,var(--card));box-shadow:0 0 0 1px var(--stop)}
.boxes input.nope{animation:nope .35s}
@keyframes nope{0%,100%{transform:none}25%{transform:translateX(-3px)}75%{transform:translateX(3px)}}
.rangetip{color:var(--muted);font-size:12px;margin-left:52px;min-height:1.3em}
.rangetip.warn{color:var(--stop)}
.smallbtn{font:600 12px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:3px 9px;
border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--accent);cursor:pointer;margin-left:6px}
.smallbtn[hidden]{display:none}
.lenwarn{color:var(--stop);font-weight:700;font-size:13px;margin-top:6px}
.lenwarn[hidden]{display:none}
.smallbtn:disabled{opacity:.4;cursor:default}
.rangewarn{display:none;color:var(--stop);font-weight:600;font-size:13px;margin-left:52px}
.rangewarn.show{display:block}
.linkbtn{background:none;border:0;padding:0;color:var(--accent);font:inherit;font-size:13px;font-weight:600;cursor:pointer}
.textin{width:100%;font:14px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:8px 10px;
border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink)}
.fontstat{font-size:12px;margin-top:4px;min-height:1.3em;color:var(--muted)}
.fontstat.ok{color:var(--accent)} .fontstat.bad{color:var(--warn)}
.fontrow{display:flex;gap:12px;align-items:flex-start;flex-wrap:wrap}
.fontrow .textin{flex:1 1 220px;width:auto;min-width:0}
.outlinebox{flex:1 1 200px;font-size:14px;padding-top:7px}
.outlinewarn{display:block;font-size:12px;font-weight:600;color:var(--warn)}
.outlinebox .hint{display:block}
#outlinereq{display:block}
.outlinebox.forced{cursor:not-allowed}
.caution{margin-top:6px;padding:8px 10px;border-radius:8px;font-size:13px;font-weight:600;
background:#f5e3c8;color:#5a3b00}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]) .caution{background:#3a2c14;color:#f0cf96}}
:root[data-theme=dark] .caution{background:#3a2c14;color:#f0cf96}
.titlebar{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.brand{display:flex;align-items:center;gap:14px}
.logobtn{background:none;border:0;padding:4px 6px;margin:-4px -6px;border-radius:10px;cursor:pointer;
color:var(--ink);line-height:0;flex:none}
.logobtn:hover{background:var(--card)}
.logobtn:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.logo{width:auto;height:90px;display:block}
.vh{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.brand .sub{max-width:300px}
#quit{margin-top:4px}
.repeatopts{display:flex;flex-direction:column;gap:6px;margin-top:10px}
.presets{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.presets select,.presets input{font:14px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:7px 9px;
border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink)}
.presets select{min-width:180px}
.presets input{flex:1;min-width:160px}
.diskwarn{color:var(--stop);font-weight:700;font-size:13px;margin-top:8px}
.diskwarn[hidden]{display:none}
.closed{max-width:520px;margin:80px auto;text-align:center;color:var(--muted)}
.engraverow{border-top:1px solid var(--line);margin-top:14px;padding-top:12px;display:flex;flex-direction:column;gap:8px}
.engravestat{color:var(--muted);font-size:13px;white-space:pre-wrap;overflow-wrap:anywhere}
.engravestat.bad{color:var(--stop)}
#previewframe{width:100%;height:900px;border:1px solid var(--line);border-radius:8px;background:#fff}
#previewcard[hidden]{display:none}
.previewnotes{font-size:13px;color:var(--muted);white-space:pre-wrap;margin-bottom:8px}
.previewnotes.bad{color:var(--stop)}
.footlinks{text-align:center;font-size:13px;margin-top:6px}
.footlinks a{color:var(--accent)}
.tick{display:flex;gap:8px;align-items:baseline;cursor:pointer}
.tick input{accent-color:var(--accent)}
.radios{display:flex;flex-direction:column;gap:8px}
.radios label{display:flex;gap:8px;align-items:baseline;cursor:pointer}
.radios input{accent-color:var(--accent)}
.path{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;color:var(--muted);word-break:break-all}
.pathrow{display:flex;gap:8px;margin-top:2px;padding-left:24px}
.pathrow input{flex:1;min-width:0;font:13px ui-monospace,Menlo,Consolas,monospace;padding:8px 10px;
border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink)}
.pathrow button{padding:8px 14px}
details.adv{border-top:1px solid var(--line);margin:4px 0 16px;padding-top:12px}
details.adv summary{cursor:pointer;font-weight:600;color:var(--muted);font-size:14px}
details.adv[open] summary{margin-bottom:12px}
.enh{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}
@media (max-width:480px){.enh{grid-template-columns:repeat(2,1fr)}}
.enh small{display:block;font-weight:400;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;font-size:11px;opacity:.8}
.summary{background:var(--accent-soft);border-radius:8px;padding:10px 12px;font-size:14px}
.summary.big{background:#f5e3c8;color:#5a3b00}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]) .summary.big{background:#3a2c14;color:#f0cf96}}
:root[data-theme=dark] .summary.big{background:#3a2c14;color:#f0cf96}
.lock{color:var(--muted);font-size:13px;margin-top:10px;min-height:1.2em}
fieldset{border:0;padding:0;margin:0;min-width:0}
fieldset:disabled{opacity:.6}
.top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.pill{font-size:12px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;
padding:4px 10px;border-radius:999px;background:var(--track);color:var(--muted)}
.pill.running,.pill.done{background:var(--accent);color:var(--accent-ink)}
.pill.paused{background:var(--warn);color:#1d1400}
.pill.stopped,.pill.error{background:var(--stop);color:#fff}
.btns{display:flex;gap:8px;flex-wrap:wrap;flex:1;justify-content:flex-end}
button{font:inherit;font-weight:600;border:1px solid var(--line);background:var(--card);color:var(--ink);
padding:9px 18px;border-radius:8px;cursor:pointer}
button:disabled{opacity:.4;cursor:default}
#start{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
#stop:not(:disabled){color:var(--stop);border-color:var(--stop)}
#reset{color:var(--muted)}
.bar{height:12px;background:var(--track);border-radius:6px;overflow:hidden;margin:16px 0 6px}
.fill{height:100%;width:0;background:var(--accent);transition:width .2s}
.barline{display:flex;justify-content:space-between;color:var(--muted);font-size:13px;
font-variant-numeric:tabular-nums}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-top:14px}
.stat .k{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.stat .v{font-size:18px;font-weight:600;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.card{min-width:0;overflow-wrap:anywhere}
h2 .mono{overflow-wrap:anywhere;word-break:break-all}
ul li{overflow-wrap:anywhere}
.msg{color:var(--muted);font-size:14px;margin-top:12px;min-height:1.4em;overflow-wrap:anywhere}
pre{margin:0;font:13px/1.6 ui-monospace,Menlo,Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;min-height:1.6em}
ul{margin:0;padding-left:18px;font:13px/1.7 ui-monospace,Menlo,Consolas,monospace;max-height:180px;overflow:auto}
.empty{color:var(--muted);font-size:14px}
/* ---- layout: settings on the left, the run panel on the right ---- */
main{max-width:1180px}
.titlebar{align-items:center;margin-bottom:18px}
.sub{margin:0}
.toplinks{display:flex;align-items:center;gap:14px;font-size:13px}
@media (max-width:560px){.titlebar{flex-wrap:wrap}.toplinks{margin-left:auto}.presetsave{margin-left:0;width:100%}.presetsave input{flex:1}}
.toplinks a{color:var(--accent)}
#quit{margin-top:0}
.layout{display:grid;grid-template-columns:minmax(0,1fr) 380px;gap:20px;align-items:start}
.runcol{position:sticky;top:16px;max-height:calc(100vh - 32px);overflow:auto;border-radius:12px}
@media (max-width:960px){.layout{grid-template-columns:1fr}.runcol{position:static;max-height:none}}
.setcol{min-width:0}
/* presets: one slim row */
.presetbar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:12px;font-size:13px}
.presetlabel{color:var(--muted);font-weight:600;margin-right:2px}
.presetbar select,.presetbar input{font:13px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:5px 8px;
border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)}
.presetbar .smallbtn{margin-left:0}
.presetsave{display:flex;gap:6px;margin-left:auto}
.presetsave input{width:190px}
.lock{margin:0 0 10px;min-height:0}
.lock:empty{display:none}
/* steps */
.step{background:var(--card);border:1px solid var(--line);border-radius:12px;margin-bottom:12px}
section.step{padding:18px 20px 6px}
details.step > summary{list-style:none;cursor:pointer;padding:15px 20px;display:flex;align-items:center;gap:14px}
details.step > summary::-webkit-details-marker{display:none}
details.step > summary::after{content:"";margin-left:auto;flex:none;width:8px;height:8px;border-right:2px solid var(--muted);
border-bottom:2px solid var(--muted);transform:rotate(45deg);transition:transform .15s}
details.step[open] > summary::after{transform:rotate(-135deg)}
details.step[open] > summary{border-bottom:1px solid var(--line)}
.stepbody{padding:16px 20px 6px}
.stephead{display:flex;align-items:center;gap:10px;margin:0;font-size:16px;color:var(--ink);text-transform:none;letter-spacing:0;font-weight:650}
section.step .stephead{margin-bottom:16px}
.stepno{display:inline-grid;place-items:center;width:24px;height:24px;border-radius:50%;background:var(--accent-soft);
color:var(--accent);font-size:13px;font-weight:700;flex:none}
.stepsum{color:var(--muted);font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
details.step[open] .stepsum{display:none}
details.adv{border-top:1px solid var(--line);margin:0 0 12px;padding-top:0}
details.adv summary{font-size:inherit;color:inherit}
details.adv[open] summary{margin-bottom:0}
/* range, behind its own switch */
.rangebox{border-top:1px solid var(--line);margin:4px -20px 0;padding:0 20px}
.rangebox > summary{cursor:pointer;padding:12px 0;display:flex;gap:10px;align-items:baseline;font-weight:600;font-size:14px;color:var(--accent)}
.rangebox > summary .hint{font-weight:400}
.rangeinner{padding-bottom:12px}
/* (i) tips replace the always-visible grey hints */
.info{display:inline-grid;place-items:center;width:17px;height:17px;padding:0;border-radius:50%;border:1px solid var(--line);
background:var(--card);color:var(--muted);font:700 11px/1 Georgia,serif;font-style:italic;cursor:help;position:relative;
vertical-align:1px;margin-left:6px;flex:none}
.info:hover,.info:focus-visible{color:var(--accent);border-color:var(--accent);outline:none}
.info::after{content:attr(data-tip);position:absolute;left:50%;bottom:calc(100% + 8px);transform:translateX(-50%);
width:max-content;max-width:280px;padding:8px 10px;border-radius:8px;background:var(--ink);color:var(--bg);
font:400 12.5px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;font-style:normal;text-align:left;
white-space:normal;opacity:0;pointer-events:none;transition:opacity .12s;z-index:20;box-shadow:0 4px 14px rgba(0,0,0,.18)}
.info:hover::after,.info:focus-visible::after{opacity:1}
.fhead{align-items:center}
.fhead > .info{margin-right:auto}
.fhead > strong{margin-left:auto}
.field{margin-bottom:20px}
.caution[hidden],.outlinewarn[hidden],.outlinewarn:empty{display:none}
/* the run panel */
.runcard{padding:18px}
.runcard .summary{font-size:14px;line-height:1.45}
.runbtns{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:14px}
.runbtns #start{grid-column:1/-1;padding:11px 18px;font-size:16px}
.runbtns button:not(#start){padding:8px 10px;font-size:14px}
.barline{align-items:center}
.barline .pill{font-size:10.5px;padding:2px 8px}
.stepsum{font-weight:400}
.btns2 button[hidden]{display:none}
#pause,#stop,#reset{background:transparent}
.bar{margin:14px 0 6px;height:8px}
.stats{grid-template-columns:auto minmax(0,1fr) auto;gap:8px 18px;margin-top:10px}
.stat .k{font-size:11px}
.stat .v{font-size:15px}
.msg{margin-top:10px;font-size:13px}
.msg:empty{display:none}
.engraverow{margin-top:14px;padding-top:14px}
.btns2{display:flex;gap:8px;flex-wrap:wrap}
.btns2 button{padding:8px 12px;font-size:14px}
.engravestat:empty{display:none}
#previewcard{border-top:1px solid var(--line);margin-top:14px;padding-top:12px}
.sechead{display:flex;justify-content:space-between;align-items:baseline;font-size:13px;font-weight:600;color:var(--muted);margin-bottom:6px}
.sechead .linkbtn{font-size:13px}
.sechead .linkbtn[hidden]{display:none}
.winnote{background:var(--accent-soft);border-radius:10px;padding:10px 14px;font-size:13.5px;margin:0 0 14px;overflow-wrap:anywhere}
.winnote[hidden]{display:none}
.winnote a{color:var(--accent);font-weight:600}
.runsec{border-top:1px solid var(--line);margin-top:14px;padding-top:10px}
.runsec > summary{cursor:pointer;font-size:13px;font-weight:600;color:var(--muted);padding:2px 0 6px}
.runsec .path{margin-bottom:6px}
</style></head><body><main>
<div class="titlebar">
  <div class="brand"><button type="button" class="logobtn" id="themetoggle" title="Switch to dark mode" aria-label="Melodarium. Switch to dark mode"><svg class="logo" viewBox="34 42 502 263" aria-hidden="true"><g transform="translate(0 23.7)"><g fill="none" stroke="currentColor" stroke-width="2.7" stroke-linecap="round" stroke-linejoin="round"><path d="M 42 115 C 110 131.75 134 11 203 29 S 297 139.5 363 89 S 450 17 520 65"/><path d="M 42 115 C 110 141.75 134 43 203 61 S 297 169.5 363 121 S 450 49 520 65"/><path d="M 42 115 C 110 153.75 134 75 203 93 S 297 199.5 363 153 S 450 81 520 65"/><path d="M 42 115 C 110 165.75 134 107 203 125 S 297 229.5 363 185 S 450 113 520 65"/></g><g fill="currentColor"><circle cx="154.82" cy="39.6" r="8"/><circle cx="297.34" cy="94.44" r="8"/><circle cx="520" cy="65" r="8"/></g></g><path transform="translate(0 47.13)" fill="currentColor" d="m 157.89603,250 -9.984,-25.467 h -0.117 q 0.039,1.092 0.078,2.496 0.078,1.365 0.078,2.886 V 250 h -2.145 v -27.846 h 3.432 l 9.594,24.375 h 0.117 l 9.711,-24.375 h 3.354 V 250 h -2.262 v -20.319 q 0,-1.287 0.039,-2.613 0.078,-1.365 0.117,-2.496 h -0.117 L 159.72903,250 Z m 44.20598,0 h -15.288 v -27.846 h 15.288 v 2.028 h -13.026 v 10.179 h 12.285 v 2.028 h -12.285 v 11.583 h 13.026 z m 13.27898,0 v -27.846 h 2.262 v 25.779 h 13.065 V 250 Z m 49.89996,-13.962 q 0,4.251 -1.404,7.488 -1.404,3.237 -4.212,5.07 -2.769,1.794 -6.903,1.794 -4.212,0 -7.02,-1.794 -2.769,-1.833 -4.173,-5.07 -1.365,-3.276 -1.365,-7.527 0,-4.251 1.404,-7.449 1.443,-3.198 4.251,-4.992 2.847,-1.833 7.02,-1.833 4.017,0 6.786,1.755 2.769,1.716 4.173,4.914 1.443,3.198 1.443,7.644 z m -22.698,-0.039 q 0,3.705 1.092,6.513 1.092,2.769 3.354,4.329 2.262,1.521 5.733,1.521 3.51,0 5.733,-1.521 2.262,-1.521 3.315,-4.29 1.092,-2.808 1.092,-6.513 0,-5.811 -2.535,-9.048 -2.496,-3.237 -7.488,-3.237 -3.471,0 -5.772,1.56 -2.301,1.521 -3.432,4.29 -1.092,2.73 -1.092,6.396 z m 57.46599,-0.195 q 0,7.02 -3.744,10.608 -3.705,3.588 -10.764,3.588 h -6.903 v -27.846 h 7.761 q 6.591,0 10.101,3.51 3.549,3.471 3.549,10.14 z m -2.379,0.078 q 0,-11.739 -11.739,-11.739 h -5.031 v 23.868 h 4.446 q 12.324,0 12.324,-12.129 z m 32.35,14.118 -3.705,-9.594 h -11.544 l -3.744,9.594 h -2.34 l 10.959,-27.963 h 2.067 l 10.686,27.963 z m -8.112,-21.684 q -0.234,-0.546 -0.624,-1.716 -0.39,-1.17 -0.663,-2.067 -0.312,1.053 -0.663,2.067 -0.351,1.014 -0.585,1.755 l -3.861,9.984 h 10.101 z m 28.33299,-6.162 q 4.992,0 7.488,1.755 2.535,1.716 2.535,5.889 0,3.198 -1.716,5.031 -1.677,1.794 -4.212,2.535 l 7.644,12.636 h -2.691 l -7.098,-12.012 h -6.63 V 250 h -2.262 v -27.846 z m -0.195,1.989 h -4.485 v 11.895 h 5.265 q 3.393,0 5.226,-1.56 1.872,-1.599 1.872,-4.602 0,-3.198 -1.95,-4.446 -1.95,-1.287 -5.928,-1.287 z M 379.97794,250 h -8.19 v -1.404 l 2.964,-0.429 v -24.141 l -2.964,-0.468 v -1.404 h 8.19 v 1.404 l -2.964,0.468 v 24.141 l 2.964,0.429 z m 33.48104,-9.828 q 0,4.758 -2.769,7.488 -2.73,2.73 -7.761,2.73 -5.031,0 -7.722,-2.73 -2.652,-2.73 -2.652,-7.566 v -17.94 h 2.262 v 17.94 q 0,4.056 2.106,6.162 2.106,2.106 6.123,2.106 3.939,0 6.045,-2.106 2.145,-2.145 2.145,-5.928 v -18.174 h 2.223 z m 26.61701,9.828 -9.984,-25.467 h -0.117 q 0.039,1.092 0.078,2.496 0.078,1.365 0.078,2.886 V 250 h -2.145 v -27.846 h 3.432 l 9.594,24.375 h 0.117 l 9.711,-24.375 h 3.354 V 250 h -2.262 v -20.319 q 0,-1.287 0.039,-2.613 0.078,-1.365 0.117,-2.496 h -0.117 L 441.90899,250 Z"/></svg></button>
  <div><h1 class="vh">Melodarium</h1>
  <p class="sub">Every arrangement of the notes you pick, written as LilyPond scores.</p></div></div>
  <div class="toplinks"><a href="/acknowledgements" target="_blank" id="acklink">Acknowledgements</a>
    <button type="button" id="quit" title="Save progress and close the app">Quit</button></div>
</div>

<div class="winnote" id="winnote" hidden></div>
<div class="layout">
<section class="setcol" aria-label="Settings">
  <div class="presetbar">
    <span class="presetlabel">Preset</span>
    <select id="presetsel" aria-label="Saved presets"><option value="">Saved presets…</option></select>
    <button type="button" class="smallbtn" id="presetload">Load</button>
    <button type="button" class="smallbtn" id="presetdel">Delete</button>
    <span class="presetsave"><input id="presetname" type="text" maxlength="60" placeholder="Save current settings as…" autocomplete="off">
    <button type="button" class="smallbtn" id="presetsave">Save</button></span>
  </div>
  <div class="lock" id="lock"></div>
  <fieldset id="settings">

  <section class="step open" id="step-notes">
    <h2 class="stephead"><span class="stepno">1</span>Notes</h2>
    <div class="field">
      <div class="fhead"><label for="len">Notes per permutation</label><strong id="lenv">4</strong></div>
      <input type="range" id="len" min="2" max="24" step="1">
      <div class="lenwarn" id="lenwarn" hidden>Warning! File sizes get exponentially bigger beyond this point!</div>
    </div>
    <div class="field">
      <div class="fhead"><span>Accidentals</span></div>
      <div class="seg" id="spellings"></div>
    </div>
    <div class="field">
      <div class="fhead"><span>Notes to use</span><span><span class="hint" id="pickcount"></span><button type="button" class="smallbtn" id="pickall">Select all</button><button type="button" class="smallbtn" id="picknone">Select none</button></span></div>
      <div class="chips" id="chips"></div>
      <div class="repeatopts">
        <label class="tick"><input type="checkbox" id="rm_norepeat">
          <span>Exclude repeated notes <span class="hint">No note twice in a row.</span></span></label>
        <label class="tick"><input type="checkbox" id="rm_once">
          <span>Use each note once <span class="hint">No note repeats anywhere. Needs at least as many ticked notes as the permutation is long.</span></span></label>
      </div>
    </div>
    <details class="rangebox" id="rangebox">
      <summary><span>Only part of the list…</span><span class="hint" id="rangeinfo"></span></summary>
      <div class="rangeinner">
        <div class="fhead"><span class="hint dyn">From the Start permutation to the End one, both included.</span>
          <button type="button" class="smallbtn" id="fullrange" hidden>Reset to full range</button></div>
        <div class="rangerow" id="rstartrow"><span class="rlabel">Start</span><div class="boxes" id="rstart"></div></div>
        <div class="rangerow" id="rendrow"><span class="rlabel">End</span><div class="boxes" id="rend"></div></div>
        <div class="rangewarn" id="rangewarn">Permutation not possible — the ending must come after the starting permutation.</div>
        <div class="rangetip" id="rangetip">Type a note in each box (e.g. a, ais, bes); the cursor moves on by itself.</div>
      </div>
    </details>
  </section>

  <details class="step" id="step-notation">
    <summary><h2 class="stephead"><span class="stepno">2</span>Notation</h2><span class="stepsum" id="sum-notation"></span></summary>
    <div class="stepbody">
      <div class="two">
        <div class="field">
          <div class="fhead"><span>Clef</span></div>
          <div class="seg" id="clefs"></div>
        </div>
        <div class="field">
          <div class="fhead"><span>Octave</span><span class="hint">c' is middle C; notes run from the A a third below the chosen C up to the G♯ above it.</span></div>
          <div class="seg" id="pitches"></div>
        </div>
      </div>
      <div class="field">
        <div class="fhead"><span>Note placement</span><span class="hint dyn" id="placehint"></span></div>
        <div class="seg" id="placements"></div>
      </div>
      <div class="field">
        <label class="tick"><input type="checkbox" id="chunklabels">
          <span>Chunk labels <span class="hint">Labels above the staff where a new block of the list begins, e.g. A B × × marks the start of all permutations beginning A B.</span></span></label>
      </div>
    </div>
  </details>

  <details class="step" id="step-pages">
    <summary><h2 class="stephead"><span class="stepno">3</span>Pages</h2><span class="stepsum" id="sum-pages"></span></summary>
    <div class="stepbody">
      <div class="field">
        <div class="fhead"><label for="staff">Staff size</label><strong id="staffv">20</strong></div>
        <input type="range" id="staff" min="10" max="30" step="1">
      </div>
      <div class="field">
        <div class="fhead"><label for="firstsys">Systems on the first page</label><span class="hint">Each PDF's first page, which also holds the title.</span><strong id="firstsysv">10</strong></div>
        <input type="range" id="firstsys" min="1" max="12" step="1">
        <div class="lenwarn" id="firstsyswarn" hidden></div>
      </div>
      <div class="field">
        <div class="fhead"><label for="systems">Systems on the other pages</label><strong id="systemsv">12</strong></div>
        <input type="range" id="systems" min="1" max="12" step="1">
        <div class="lenwarn" id="syswarn" hidden></div>
      </div>
      <div class="two">
        <div class="field">
          <div class="fhead"><label for="ppdf">Pages per PDF</label><span class="hint">1 to 10,000. Each PDF is one LilyPond book.</span></div>
          <input class="textin" id="ppdf" type="text" inputmode="numeric" maxlength="5" autocomplete="off" style="width:120px">
        </div>
        <div class="field">
          <div class="fhead"><span>PDF links</span><span class="hint">Point-and-click: clicking a note in the PDF opens its line in the .ly file. Links make PDFs bigger and store this folder's path inside them.</span></div>
          <div class="seg" id="pdflinks"></div>
        </div>
      </div>
    </div>
  </details>

  <details class="step" id="step-files">
    <summary><h2 class="stephead"><span class="stepno">4</span>Files &amp; saving</h2><span class="stepsum" id="sum-files"></span></summary>
    <div class="stepbody">
      <div class="field">
        <div class="fhead"><span>Save to</span></div>
        <div class="radios">
          <label><input type="radio" name="savemode" value="default">
            <span><span id="defaultplace">Next to this program</span> <span class="path" id="scriptdir"></span></span></label>
          <label><input type="radio" name="savemode" value="custom"><span>Another folder</span></label>
          <div class="pathrow">
            <input type="text" id="savepath" placeholder="Type a folder path or use Browse" spellcheck="false">
            <button type="button" id="browse">Browse…</button>
          </div>
        </div>
      </div>
      <div class="field">
        <div class="fhead"><label for="kb">Max file size</label><span class="hint">Each .ly score file (and text list) is closed before it passes this size.</span><strong id="kbv">1000 KB</strong></div>
        <input type="range" id="kb" min="500" max="1500" step="50">
      </div>
      <div class="field">
        <label class="tick"><input type="checkbox" id="wtxt">
          <span>Also save plain-text lists <span class="hint">.txt files, one permutation per line, no LilyPond; split at the same size limit.</span></span></label>
      </div>
    </div>
  </details>

  <details class="step adv" id="adv">
    <summary><h2 class="stephead"><span class="stepno">5</span>Advanced</h2><span class="stepsum" id="sum-adv"></span></summary>
    <div class="stepbody">
      <div class="field">
        <div class="fhead"><label for="lppath">LilyPond program</label><span class="hint dyn" id="lpstatus">looking for LilyPond…</span></div>
        <div class="presets">
          <input id="lppath" type="text" placeholder="Leave blank to find it automatically" spellcheck="false" autocomplete="off">
          <button type="button" class="smallbtn" id="lpuse">Use this</button>
          <button type="button" class="smallbtn" id="lpauto">Find automatically</button>
        </div>
        <div class="lenwarn" id="lpwarn" hidden></div>
      </div>
      <div class="field">
        <div class="fhead"><span>LilyPond version</span><span class="hint">The files are written in this version's syntax.</span></div>
        <div class="seg" id="lpversions"></div>
      </div>
      <div class="field">
        <div class="fhead"><span>Enharmonic spellings</span><span class="hint">Ticked ones replace the usual note.</span></div>
        <div class="chips enh" id="enh"></div>
      </div>
      <div class="field">
        <label class="tick"><input type="checkbox" id="norepeat">
          <span>Don't repeat the accidental on an immediately repeated note
            <span class="hint">A♯ A♯ prints as A♯ A; the spacing stays the same.</span></span></label>
      </div>
      <div class="field">
        <div class="fhead"><label for="textfont">Text font</label><span class="hint">Blank = LilyPond's default. Fonts come from this computer.</span></div>
        <input class="textin" id="textfont" list="fontlist" placeholder="Start typing a font name…" spellcheck="false" autocomplete="off">
        <datalist id="fontlist"></datalist>
        <div class="fontstat" id="textfontstat"></div>
      </div>
      <div class="field">
        <div class="fhead"><label for="musicfont">Music font</label><span class="hint">Blank = Emmentaler (LilyPond's own). A font's files must be installed in LilyPond's own fonts folder (see LilyPond's “Replacing the notation font”).</span></div>
        <div class="fontrow">
          <input class="textin" id="musicfont" list="musicfontlist" placeholder="Pick from the list or type a name" spellcheck="false" autocomplete="off">
          <label class="tick outlinebox" id="outlinelabel"><input type="checkbox" id="outline"><span>Output music to outline
            <span class="hint">Music symbols become shapes; text stays selectable.</span>
            <span class="outlinewarn" id="outlinewarn"></span>
            <span class="hint dyn" id="outlinereq" hidden></span></span></label>
        </div>
        <datalist id="musicfontlist"></datalist>
        <div class="fontstat" id="musicfontstat"></div>
        <div class="caution" id="musicwarn"></div>
      </div>
    </div>
  </details>
  </fieldset>
</section>

<aside class="runcol" aria-label="Run">
  <div class="card runcard">
    <div class="summary" id="summary"></div>
    <div class="diskwarn" id="diskwarn" hidden></div>
    <div class="runbtns">
      <button id="start">Start</button>
      <button id="pause">Pause</button>
      <button id="stop">Stop</button>
      <button id="reset">Reset</button>
    </div>
    <div class="bar"><div class="fill" id="fill"></div></div>
    <div class="barline"><span id="pct">0%</span><span class="pill" id="pill">idle</span><span id="count">0 / 0</span></div>
    <div class="stats">
      <div class="stat"><div class="k">Elapsed</div><div class="v" id="elapsed">00:00:00</div></div>
      <div class="stat"><div class="k">Chunk</div><div class="v mono" id="chunk">–</div></div>
      <div class="stat"><div class="k">Files</div><div class="v" id="nfiles">0</div></div>
    </div>
    <div class="msg" id="msg"></div>
    <div class="engraverow">
      <div class="btns2">
        <button id="preview" title="Engrave the first page with the current settings">Preview first page</button>
        <button id="engrave" title="Engrave every finished score file into PDFs, one at a time">Engrave PDFs</button>
        <button id="engravestop">Stop engraving</button>
      </div>
      <div class="engravestat" id="engravestat"></div>
    </div>
    <div id="previewcard" hidden>
      <div class="sechead"><span>Preview · first page</span><button type="button" class="linkbtn" id="previewagain">Open it again</button></div>
      <div class="previewnotes" id="previewnotes"></div>
    </div>
    <details class="runsec" id="recentbox">
      <summary>Latest bars</summary>
      <pre id="recent"></pre>
    </details>
    <details class="runsec" id="filesbox" open>
      <summary>Finished files</summary>
      <div class="path" id="outdir"></div>
      <div id="files"></div>
    </details>
  </div>
</aside>
</div>
</main>
<script>
const $ = id => document.getElementById(id);
// ---- light / dark: follows the system until the logo is clicked, then switches ----
// (remembered while the panel is open, e.g. across a reload; each new start follows the system)
const DARK_MQ = window.matchMedia("(prefers-color-scheme: dark)");
let THEME = null;
try { THEME = sessionStorage.getItem("melodarium-theme"); } catch(e){}
function effectiveTheme(){ return THEME || (DARK_MQ.matches ? "dark" : "light"); }
function applyTheme(){
  if (THEME) document.documentElement.dataset.theme = THEME;
  else delete document.documentElement.dataset.theme;
  const next = effectiveTheme() === "dark" ? "light" : "dark", b = $("themetoggle");
  b.title = "Switch to " + next + " mode";
  b.setAttribute("aria-label", "Melodarium. Switch to " + next + " mode");
  $("acklink").href = "/acknowledgements?theme=" + effectiveTheme();
}
$("themetoggle").onclick = () => {
  THEME = effectiveTheme() === "dark" ? "light" : "dark";
  try { sessionStorage.setItem("melodarium-theme", THEME); } catch(e){}
  applyTheme();
};
DARK_MQ.addEventListener("change", applyTheme);
applyTheme();
// The grey explanations become small (i) tips: point at one (or tab to it) to read it.
document.querySelectorAll(".hint:not([id]):not(.dyn)").forEach(h => {
  const tip = document.createElement("span"), text = h.textContent.trim();
  tip.className = "info"; tip.textContent = "i"; tip.tabIndex = 0;
  tip.dataset.tip = text; tip.setAttribute("role", "img"); tip.setAttribute("aria-label", text);
  tip.onclick = e => e.preventDefault();        // inside a label: don't tick its box
  h.replaceWith(tip);
});
let INIT = null, rangeShown = false, advShown = false;
// one-line summaries on the closed steps, e.g. "staff 20 · 10 / 12 systems · ..."
function renderSteps(){
  if (!INIT || !draft) return;
  const lab = (m, v) => (m && m[v]) || v;
  $("sum-notation").textContent = lab(INIT.clefs, draft.clef) + " clef · octave " + draft.pitch +
    " · " + lab(INIT.placements, draft.placement).toLowerCase() +
    (draft.chunk_labels === false ? " · no chunk labels" : "");
  $("sum-pages").textContent = "staff " + draft.staff_size + " · " + draft.first_page_systems + " / " +
    draft.systems_per_page + " systems · " + Number(draft.pages_per_pdf).toLocaleString() + " pages per PDF · " +
    lab(INIT.pdf_links, draft.pdf_links).toLowerCase();
  $("sum-files").textContent = (draft.save_mode === "custom" ? (draft.save_path.trim() || "another folder")
                                                              : $("defaultplace").textContent.toLowerCase()) +
    " · " + draft.max_kb.toLocaleString() + " KB files" + (draft.write_txt ? " · plus text lists" : "");
  const mf = draft.music_font.trim(), tf = draft.text_font.trim();
  $("sum-adv").textContent = "LilyPond " + lab(INIT.lilypond_versions, draft.lilypond) + " · " + (mf || "Emmentaler") +
    ((draft.outline_fonts || outlineRequired()) ? " (outline)" : "") + (tf ? " · " + tf : "") +
    (draft.enh.length ? " · " + draft.enh.join(", ") : "") + (draft.no_repeat_acc ? " · repeated accidentals hidden" : "");
  // a run that uses only part of the list shows its range
  if (!rangeShown && !rangeIsFull()){ $("rangebox").open = true; rangeShown = true; }
}
const pad = n => String(n).padStart(2, "0");
function fmtTime(s){ s = Math.floor(s); const d = Math.floor(s/86400); s %= 86400;
  const t = pad(Math.floor(s/3600)) + ":" + pad(Math.floor(s%3600/60)) + ":" + pad(s%60);
  return d ? d + "d " + t : t; }
function fmtBytes(b){ const u = ["bytes","KB","MB","GB","TB","PB","EB","ZB","YB"]; let i = 0;
  while (b >= 1000 && i < u.length-1){ b /= 1000; i++; }
  return (i ? b.toFixed(b < 10 ? 1 : 0) : Math.round(b)) + " " + u[i]; }

let SETS = null, ENH = null, ALL = [], chipsFor = null;
let draft = null, picked = [], status = "idle", locked = false;
let note = "", noteUntil = 0;
let FONTS = null, FONT_SOURCE = "";
function say(text){ note = text; noteUntil = Date.now() + 6000; $("msg").textContent = text; }

// The 12 names for the current spelling, with ticked enharmonics swapped in.
function effSet(spelling, enh){
  const swap = {}; enh.forEach(e => { swap[ENH[e]] = e; });
  return SETS[spelling].map(n => swap[n] || n);
}
function setKey(){ return draft.spelling + "|" + draft.enh.slice().sort().join(","); }
// Keep the same pitches ticked when the note names change (b <-> ces, ais <-> bes...).
function respell(change){
  const before = effSet(draft.spelling, draft.enh);
  change();
  const after = effSet(draft.spelling, draft.enh);
  const map = n => before.includes(n) ? after[before.indexOf(n)] : n;
  picked = picked.map(map);
  if (draft.rstart) draft.rstart = draft.rstart.map(map);
  if (draft.rend) draft.rend = draft.rend.map(map);
}

function buildEnh(){
  const box = $("enh"); box.innerHTML = "";
  Object.entries(ENH).forEach(([name, replaces]) => {
    const l = document.createElement("label"); l.className = "chip";
    const input = document.createElement("input"); input.type = "checkbox"; input.value = name;
    input.onchange = () => {
      respell(() => {
        draft.enh = input.checked ? draft.enh.concat(name) : draft.enh.filter(x => x !== name);
      });
      renderSettings();
    };
    const span = document.createElement("span");
    span.innerHTML = name + "<small>instead of " + replaces + "</small>";
    l.append(input, span); box.appendChild(l);
  });
}

function buildChips(){
  ALL = effSet(draft.spelling, draft.enh); chipsFor = setKey();
  const box = $("chips"); box.innerHTML = "";
  ALL.forEach(n => {
    const l = document.createElement("label"); l.className = "chip";
    l.innerHTML = '<input type="checkbox" value="' + n + '"><span>' + n + "</span>";
    l.firstChild.onchange = e => {
      if (e.target.checked) picked.push(n); else picked = picked.filter(x => x !== n);
      renderSettings();
    };
    box.appendChild(l);
  });
}

function buildSeg(boxId, name, options, onPick){
  const box = $(boxId); box.innerHTML = "";
  options.forEach(([value, label, mono]) => {
    const l = document.createElement("label");
    const input = document.createElement("input");
    input.type = "radio"; input.name = name; input.value = value;
    input.onchange = () => { if (onPick) onPick(value); draft[name] = value; renderSettings(); };
    const span = document.createElement("span"); span.textContent = label;
    if (mono) span.className = "mono";
    l.append(input, span); box.appendChild(l);
  });
}

function ordered(){ return ALL.filter(n => picked.includes(n)); }

// ---- range (start / end permutation): one typed box per note ----
let rangeKey = "", rangeBad = false, tipTimer = 0, lastFull = true;
const isName = v => ordered().includes(v);
const isPrefix = v => ordered().some(n => n.startsWith(v));
const hasLonger = v => ordered().some(n => n.length > v.length && n.startsWith(v));
// Rough estimate of how many lines of music fit on a letter page (the first page,
// which also holds the titles, is the tightest). Everything on the page scales with
// the staff size; the margins (5 mm + 6 mm) don't. Units are staff spaces.
// Systems that fit on a letter page, measured with LilyPond 2.26 (12 chromatic notes,
// 4 per bar) at staff sizes 10, 12 ... 30; odd sizes use the next even size up.
const SYSTEMS_FIT = {   // staff size: [fixed first page, fixed other pages, nearest first, nearest other]
  18: [12, 12, 11, 12], 20: [12, 12, 10, 11], 22: [10, 11, 9, 10], 24: [9, 10, 8, 9],
  26: [8, 9, 7, 8], 28: [8, 9, 6, 8], 30: [7, 8, 6, 7]};
function maxSystemsPerPage(first){
  const size = Math.max(18, Math.min(30, draft.staff_size + draft.staff_size % 2));
  const row = SYSTEMS_FIT[size];
  return row[(draft.placement === "nearest" ? 2 : 0) + (first ? 0 : 1)];
}

// ---- permutation modes; exact whole-number (BigInt) counting ----
// (12 notes at length 24 is ~7.9e25 permutations, too big for ordinary numbers)
const RM = () => draft.repeat_mode || "all";
function fallingPow(n, k){ if (k > n) return 0n; let r = 1n; for (let j = 0n; j < k; j++) r *= (n - j); return r; }
function permCount(n, k, mode){
  n = BigInt(n); k = BigInt(k);
  if (mode === "once") return fallingPow(n, k);
  if (mode === "norepeat") return n * (n - 1n) ** (k - 1n);
  return n ** k;
}
function tailCount(n, k, j, mode){          // ways to finish once j notes are chosen
  if (mode === "once") return fallingPow(n - j, k - j);
  if (mode === "norepeat") return (n - 1n) ** (k - j);
  return n ** (k - j);
}
function rangeIndex(arr, notes){             // position in alphabetical order (same as the program)
  const mode = RM(), n = BigInt(notes.length), k = BigInt(arr.length);
  const avail = notes.map((_, x) => x);
  let i = 0n, prev = -1;
  arr.forEach((t, p) => {
    const d = notes.indexOf(t); let r = d;
    if (mode === "once"){ r = avail.indexOf(d); avail.splice(r, 1); }
    else if (mode === "norepeat"){ r = (prev < 0 || d < prev) ? d : d - 1; }
    i += BigInt(r) * tailCount(n, k, BigInt(p + 1), mode); prev = d;
  });
  return i;
}
function permAllowed(arr){
  if (RM() === "once") return new Set(arr).size === arr.length;
  if (RM() === "norepeat") return arr.every((t, p) => p === 0 || t !== arr[p - 1]);
  return true;
}
function firstPerm(notes, k){
  if (RM() === "once") return notes.slice(0, k);
  if (RM() === "norepeat") return Array.from({length: k}, (_, p) => notes[p % 2]);
  return Array(k).fill(notes[0]);
}
function lastPerm(notes, k){
  const n = notes.length;
  if (RM() === "once") return notes.slice(n - k).reverse();
  if (RM() === "norepeat") return Array.from({length: k}, (_, p) => notes[n - 1 - (p % 2)]);
  return Array(k).fill(notes[n - 1]);
}
function fullCount(){ return permCount(ordered().length, draft.length, RM()); }
function noPermReason(){
  return RM() === "once"
    ? "“Use each note once” needs at least " + draft.length + " ticked notes (" + picked.length + " ticked)."
    : "“Exclude repeated notes” needs at least 2 ticked notes.";
}
function fixRange(){
  // fill / repair the boxes when the notes or length change (not while typing)
  const notes = ordered(), n = draft.length;
  if (!notes.length) return;
  if (fullCount() === 0n) return;
  const fit = (arr, fill) => Array.from({length: n}, (_, k) =>
    (arr && notes.includes(arr[k])) ? arr[k] : fill[k]);
  draft.rstart = fit(draft.rstart, firstPerm(notes, n));
  draft.rend = fit(draft.rend, lastPerm(notes, n));
}
function rangeComplete(){ return draft.rstart.every(isName) && draft.rend.every(isName); }
function rangeIsFull(){
  const notes = ordered(), a = firstPerm(notes, draft.length), z = lastPerm(notes, draft.length);
  return draft.rstart.every((t, k) => t === a[k]) && draft.rend.every((t, k) => t === z[k]);
}
function boxes(key){ return [...$(key).querySelectorAll("input")]; }
function focusBox(key, k){
  let b = boxes(key);
  if (k >= b.length && key === "rstart"){ key = "rend"; k = 0; b = boxes(key); }  // Start row -> End row
  if (k < 0 && key === "rend"){ key = "rstart"; b = boxes(key); k = b.length - 1; }
  if (k >= 0 && k < b.length){ b[k].focus(); b[k].select(); }
}
function tip(text, warn){
  const el = $("rangetip"); el.textContent = text; el.classList.toggle("warn", !!warn);
  clearTimeout(tipTimer);
  if (warn) tipTimer = setTimeout(() => tip("Type a note in each box (e.g. a, ais, bes); the cursor moves on by itself."), 3500);
}
function nope(box, ch){
  box.classList.remove("nope"); void box.offsetWidth; box.classList.add("nope");
  const allowed = ordered().join(", ");
  tip(/[a-z]/.test(ch) ? "“" + ch + "” doesn't fit here — allowed notes: " + allowed + "."
                       : "Only note names can be typed — allowed notes: " + allowed + ".", true);
}
// Put typed text into box k, letter by letter: keep it while it can still become a
// ticked note; when a full note can't grow any further, carry on in the next box.
function feed(key, k, text, prev){
  const b = boxes(key);
  if (k >= b.length){
    if (key === "rstart" && text) return feed("rend", 0, text);
    return;
  }
  if (prev === undefined) prev = draft[key][k];   // a refused letter keeps the old note
  let cur = "", moved = false;
  for (let p = 0; p < text.length; p++){
    const ch = text[p], cand = cur + ch;
    if (isPrefix(cand)){ cur = cand; continue; }
    if (isName(cur) && isPrefix(ch)){            // e.g. "a" then "c": "c" starts the next box
      draft[key][k] = cur; b[k].value = cur;
      feed(key, k + 1, text.slice(p)); moved = true; break;
    }
    nope(b[k], ch);                              // not allowed here: ignore it
  }
  if (!moved && cur === "" && text && isName(prev)){   // nothing usable typed: keep the note
    b[k].value = prev; b[k].select(); renderSettings(); return;
  }
  if (!moved){
    draft[key][k] = cur; b[k].value = cur;
    if (isName(cur) && !hasLonger(cur)) focusBox(key, k + 1);   // finished note: jump on
    else { b[k].focus(); b[k].setSelectionRange(cur.length, cur.length); }
  }
  renderSettings();
}
function buildRange(){
  const notes = ordered();
  rangeKey = draft.length + "|" + notes.join(",") + "|" + RM();
  ["rstart", "rend"].forEach(key => {
    const el = $(key); el.innerHTML = "";
    for (let k = 0; k < draft.length; k++){
      const box = document.createElement("input");
      box.type = "text"; box.maxLength = 3; box.spellcheck = false; box.autocomplete = "off";
      box.setAttribute("autocapitalize", "none");
      box.setAttribute("aria-label", (key === "rstart" ? "Start" : "End") + " note " + (k + 1));
      // clicking always selects the whole note, so typing replaces it
      box.onfocus = () => box.select();
      box.onmousedown = e => { if (document.activeElement === box){ e.preventDefault(); box.select(); } };
      box.onmouseup = e => e.preventDefault();
      box.oninput = () => {
        const raw = box.value.toLowerCase(), clean = raw.replace(/[^a-z]/g, "");
        const prev = draft[key][k];
        if (clean !== raw) nope(box, raw.replace(/[a-z]/g, "")[0] || "");
        if (!clean && raw){ box.value = prev; box.select(); return; }   // only refused characters
        box.value = ""; feed(key, k, clean, prev);
      };
      box.onpaste = e => {
        e.preventDefault();
        feed(key, k, (e.clipboardData.getData("text") || "").toLowerCase().replace(/[^a-z]/g, ""));
      };
      box.onkeydown = e => {
        const atStart = box.selectionStart === 0 && box.selectionEnd === 0;
        const atEnd = box.selectionStart === box.value.length;
        if (e.key === "Backspace" && box.value === ""){ e.preventDefault(); focusBox(key, k - 1); }
        else if ((e.key === "ArrowLeft" && atStart)){ e.preventDefault(); focusBox(key, k - 1); }
        else if ((e.key === "ArrowRight" && atEnd) || e.key === " " || e.key === "Enter"){
          e.preventDefault();
          if (e.key === "ArrowRight" || isName(box.value)) focusBox(key, k + 1);
          else if (e.key !== "ArrowRight") nope(box, "");
        }
      };
      box.onblur = () => renderSettings();
      el.appendChild(box);
    }
  });
}
function renderRange(){
  const notes = ordered();
  if (!notes.length || fullCount() === 0n){
    $("rstart").innerHTML = $("rend").innerHTML = ""; rangeKey = ""; rangeBad = notes.length > 0;
    $("rstartrow").classList.remove("bad"); $("rendrow").classList.remove("bad");
    $("rangewarn").classList.remove("show"); $("rangeinfo").textContent = notes.length ? noPermReason() : "";
    $("fullrange").hidden = true;
    if (status !== "running") $("start").disabled = !locked && rangeBad;
    return; }
  const key = draft.length + "|" + notes.join(",") + "|" + RM();
  if (rangeKey !== key || !draft.rstart || !draft.rend){
    if (rangeKey && rangeKey !== key && lastFull){ draft.rstart = null; draft.rend = null; }  // full stays full
    fixRange(); buildRange();
  }
  ["rstart", "rend"].forEach(k => boxes(k).forEach((box, i) => {
    if (document.activeElement !== box && box.value !== draft[k][i]) box.value = draft[k][i];
    box.classList.toggle("invalid", document.activeElement !== box && !isName(draft[k][i]));
  }));
  const complete = rangeComplete();
  const full = complete && rangeIsFull();
  const a = complete ? rangeIndex(draft.rstart, notes) : 0n, b = complete ? rangeIndex(draft.rend, notes) : 0n;
  const badStart = complete && !permAllowed(draft.rstart), badEnd = complete && !permAllowed(draft.rend);
  const order = complete && !badStart && !badEnd && !full && b <= a;
  rangeBad = !complete || badStart || badEnd || order;
  $("rstartrow").classList.toggle("bad", badStart);
  $("rendrow").classList.toggle("bad", badEnd || order);
  $("rangewarn").classList.toggle("show", badStart || badEnd || order);
  $("rangewarn").textContent = (badStart || badEnd)
    ? "Permutation not possible — the " + (badStart ? "Start" : "End") + " permutation " +
      (RM() === "once" ? "uses a note more than once." : "repeats a note immediately.")
    : "Permutation not possible — the ending must come after the starting permutation.";
  $("fullrange").hidden = full;
  lastFull = full;
  if (status !== "running") $("start").disabled = !locked && rangeBad;   // update right away
  const all = fullCount();
  $("rangeinfo").textContent = full ? "all permutations (" + all.toLocaleString() + ")"
    : !complete ? "finish every box" : (order || badStart || badEnd) ? ""
    : "permutations " + (a + 1n).toLocaleString() + "–" + (b + 1n).toLocaleString()
      + " (" + (b - a + 1n).toLocaleString() + " of " + all.toLocaleString() + ")";
}
// "Exclude repeated notes" and "Use each note once" (ticking one clears the other)
$("rm_norepeat").onchange = e => { draft.repeat_mode = e.target.checked ? "norepeat" : "all"; renderSettings(); };
$("rm_once").onchange = e => { draft.repeat_mode = e.target.checked ? "once" : "all"; renderSettings(); };

// ---- free disk space on the save drive ----
let DISK = null, diskFor = null, diskTimer = 0;
function diskTarget(){ return draft.save_mode === "custom" ? draft.save_path.trim() : ""; }
function checkDisk(){
  const target = diskTarget(); if (target === diskFor) return;
  diskFor = target; clearTimeout(diskTimer);
  diskTimer = setTimeout(async () => {
    try { DISK = await (await fetch("/diskfree?path=" + encodeURIComponent(target))).json(); }
    catch(e){ DISK = null; }
    renderSettings();
  }, 400);
}
function renderDisk(e){
  checkDisk();
  const w = $("diskwarn");
  if (!e || !DISK || DISK.error || DISK.free === undefined){ w.hidden = true; return; }
  const need = e.bytes + (draft.write_txt ? e.txt : 0);
  w.hidden = need <= DISK.free * 0.9;
  w.textContent = "Not enough disk space: this run needs about " + fmtBytes(need) +
    " for its score" + (draft.write_txt ? " and text" : "") + " files (the PDFs need more), but only " +
    fmtBytes(DISK.free) + " is free on that drive.";
}

// ---- presets ----
let PRESETS = {};
const PRESET_KEYS = ["length","max_kb","staff_size","systems_per_page","first_page_systems","pages_per_pdf","text_font","music_font",
  "spelling","enh","save_mode","save_path","write_txt","rstart","rend","clef","pitch","placement",
  "no_repeat_acc","lilypond","repeat_mode","pdf_links","outline_fonts","chunk_labels"];
function fillPresets(){
  const sel = $("presetsel"), keep = sel.value;
  sel.innerHTML = '<option value="">Saved presets…</option>';
  Object.keys(PRESETS).sort((a, b) => a.localeCompare(b)).forEach(n => {
    const o = document.createElement("option"); o.value = o.textContent = n; sel.appendChild(o); });
  sel.value = PRESETS[keep] ? keep : "";
}
async function loadPresets(){ try { PRESETS = await (await fetch("/presets")).json(); } catch(e){ PRESETS = {}; } fillPresets(); }
async function postPresets(path, body){
  PRESETS = await (await fetch(path, {method: "POST", headers: {"Content-Type": "application/json"},
                                     body: JSON.stringify(body)})).json();
  fillPresets();
}
$("presetsave").onclick = async () => {
  const name = $("presetname").value.trim() || $("presetsel").value;
  if (!name){ say("Type a name for the preset first."); $("presetname").focus(); return; }
  if (PRESETS[name] && !confirm("Replace the saved preset “" + name + "”?")) return;
  const preset = {notes: ordered()};
  PRESET_KEYS.forEach(k => { preset[k] = JSON.parse(JSON.stringify(draft[k] === undefined ? null : draft[k])); });
  await postPresets("/presets", {name, preset});
  $("presetsel").value = name; $("presetname").value = ""; say("Saved preset “" + name + "”.");
};
$("presetload").onclick = () => {
  const name = $("presetsel").value, p = PRESETS[name];
  if (!p){ say("Choose a saved preset to load."); return; }
  PRESET_KEYS.forEach(k => { if (p[k] !== undefined && p[k] !== null) draft[k] = JSON.parse(JSON.stringify(p[k])); });
  draft.rstart = p.rstart ? p.rstart.slice() : null; draft.rend = p.rend ? p.rend.slice() : null;
  picked = (p.notes || []).slice();
  rangeKey = ""; lastFull = !p.rstart;       // rebuild the range boxes from the preset
  renderSettings(); say("Loaded preset “" + name + "”.");
};
$("presetdel").onclick = async () => {
  const name = $("presetsel").value;
  if (!name){ say("Choose a saved preset to delete."); return; }
  if (!confirm("Delete the preset “" + name + "”?")) return;
  await postPresets("/presets/delete", {name}); say("Deleted preset “" + name + "”.");
};

// ---- LilyPond: where it is, preview, engraving ----
let LP = null;
function renderLilypond(d){
  LP = d.lilypond || null;
  const st = $("lpstatus"), w = $("lpwarn");
  if (!LP){ st.textContent = "looking for LilyPond…"; w.hidden = true; return; }
  if (LP.error){ st.textContent = "not found"; w.hidden = false;
    if (!advShown){ $("adv").open = true; advShown = true; }    // show where to fix it
    w.textContent = "LilyPond wasn't found, so Preview and Engrave are off. Type the full path to the lilypond program above, or install LilyPond."; }
  else {
    st.textContent = "LilyPond " + LP.version + " (" + LP.source + ")";
    const is224 = LP.version.startsWith("2.24.");
    const mismatch = (is224 && draft.lilypond === "2.26") || (!is224 && draft.lilypond === "2.24");
    w.hidden = !mismatch;
    w.textContent = mismatch ? "This LilyPond is " + LP.version + ": choose “" + (is224 ? "2.24" : "2.26 or newer") +
      "” under LilyPond version above, or its files won't engrave." : "";
  }
  if (document.activeElement !== $("lppath") && !$("lppath").dataset.edited)
    $("lppath").value = (LP && LP.source === "your setting") ? LP.path : "";
}
$("lppath").oninput = () => { $("lppath").dataset.edited = "1"; };
async function setLilypond(path){
  say("Checking LilyPond…");
  const r = await (await fetch("/lilypond", {method: "POST", headers: {"Content-Type": "application/json"},
                                             body: JSON.stringify({path})})).json();
  delete $("lppath").dataset.edited;
  say(r.error ? r.error : "Using LilyPond " + r.version + " (" + r.source + ").");
  poll();
}
$("lpuse").onclick = () => setLilypond($("lppath").value.trim());
$("lpauto").onclick = () => { $("lppath").value = ""; setLilypond(""); };

function renderEngrave(d){
  const e = d.engrave, s = $("engravestat");
  const haveLP = LP && !LP.error, busy = d.status === "running";
  $("preview").disabled = !haveLP || rangeBad || !estimate();
  $("engrave").disabled = !haveLP || busy || e.status === "running" || !d.file_total;
  $("engravestop").disabled = e.status !== "running";
  $("engravestop").hidden = e.status !== "running";      // only while engraving
  let text = "", bad = false;
  if (e.status === "running")
    text = "Engraving " + (e.done + 1) + " of " + e.total + ": " + e.current + "  ·  " + fmtTime(e.elapsed);
  else if (e.status === "done" || e.status === "stopped"){
    text = (e.status === "stopped" ? "Engraving stopped. " : "Engraving finished. ") + (e.done - e.skipped - e.failed_count) +
           " file(s) engraved" + (e.skipped ? ", " + e.skipped + " already up to date" : "") + ".";
  }
  if (e.failed_count){ bad = true;
    text += "\n" + e.failed_count + " file(s) had errors:" + e.failed.map(f =>
      "\n\n— " + f.file + (f.code != null ? "  (LilyPond exit code " + f.code + ")" : "") +
      (f.reasons || []).map(r => "\n   • " + r).join("") +
      (f.log ? "\n   Last lines from LilyPond:\n" + f.log.split("\n").map(l => "     " + l).join("\n") : "") +
      (f.logfile ? "\n   Full log: " + f.logfile + " (in the run folder)" : "")).join(""); }
  if (!haveLP) text = "Preview and Engrave need LilyPond (see Advanced).";
  s.textContent = text; s.classList.toggle("bad", bad);
}
$("engrave").onclick = () => send("engrave");
$("engravestop").onclick = () => send("engrave/stop");
// ---- preview: engraved, then shown in a window of its own ----
// In the app window the preview opens as another app window (pywebview); in a web
// browser it opens as a separate browser window.
const IN_APP = () => !!(window.pywebview && window.pywebview.api && window.pywebview.api.open_window);
let lastPreview = "";
const PREVIEW_FEATURES = "width=900,height=1100";
async function showPreview(url, popup){
  if (IN_APP()){
    let ok = false;
    try { ok = await window.pywebview.api.open_window(url, "Preview – first page", "preview"); } catch(e){}
    if (ok) return true;
  }
  const full = location.origin + url;
  if (popup && !popup.closed){ popup.location.href = full; return true; }
  return !!window.open(full, "nppreview", PREVIEW_FEATURES);
}
$("preview").onclick = async () => {
  const body = startBody();
  if (!body) return;
  // a browser only allows a new window straight from the click, so open it now and fill it later
  let popup = null;
  if (!IN_APP()){
    popup = window.open("", "nppreview", PREVIEW_FEATURES);
    try { if (popup) popup.document.body.innerHTML =
      '<p style="font:15px -apple-system,Segoe UI,sans-serif;color:#666;padding:28px">Engraving the preview…</p>'; } catch(e){}
  }
  $("preview").disabled = true; say("Engraving a preview of the first page…");
  try {
    const r = await (await fetch("/preview", {method: "POST", headers: {"Content-Type": "application/json"},
                                              body: JSON.stringify(body)})).json();
    const card = $("previewcard"), notes = $("previewnotes");
    card.hidden = false;
    notes.classList.toggle("bad", !r.ok);
    notes.textContent = r.ok ? (r.warnings && r.warnings.length ? "LilyPond warnings:\n" + r.warnings.join("\n") : "Engraved with no warnings.")
                             : (r.error || "The preview failed.");
    $("previewagain").hidden = !r.ok;
    if (r.ok){
      lastPreview = "/preview.pdf?t=" + Date.now();
      say(await showPreview(lastPreview, popup) ? "Preview opened in its own window."
          : "Your browser blocked the preview window: allow pop-ups for this page, or press “Open it again”.");
    } else {
      if (popup) popup.close();
      say("The preview failed: see the message under Preview.");
    }
  } catch(e){
    if (popup) popup.close();
    say("The preview failed: the app didn't answer.");
  } finally { $("preview").disabled = false; }
};
$("previewagain").onclick = () => { if (lastPreview) showPreview(lastPreview, null); };
// Acknowledgements: its own app window too, when running in the app window
$("acklink").onclick = async e => {
  if (!IN_APP()) return;                 // a browser opens it in a new tab
  e.preventDefault();
  let ok = false;
  const page = "/acknowledgements?theme=" + effectiveTheme();
  try { ok = await window.pywebview.api.open_window(page, "Acknowledgements"); } catch(err){}
  if (!ok) window.open(page, "_blank");
};
function renderWindowNote(d){
  const el = $("winnote"), text = d.window_note || "";
  if (el.dataset.text === text) return;
  el.dataset.text = text; el.hidden = !text; el.textContent = "";
  // turn a web address in the note into a link
  const m = text.match(/https?:\/\/\S+/);
  if (!m){ el.textContent = text; return; }
  el.append(text.slice(0, m.index));
  const a = document.createElement("a"); a.href = m[0]; a.target = "_blank"; a.rel = "noopener";
  a.textContent = "Microsoft's WebView2 download page"; el.append(a, text.slice(m.index + m[0].length));
}

// ---- quit ----
$("quit").onclick = async () => {
  const busy = status === "running" || status === "paused";
  if (!confirm(busy ? "Stop this run (progress is saved) and quit Melodarium?"
                    : "Quit Melodarium?")) return;
  clearInterval(pollTimer);
  try { await fetch("/quit", {method: "POST"}); } catch(e){}
  document.querySelector("main").innerHTML =
    '<div class="closed"><h1>Melodarium has closed.</h1><p>Progress is saved. You can close this tab.</p></div>';
};

$("pickall").onclick = () => { picked = ALL.slice(); renderSettings(); };
$("picknone").onclick = () => { picked = []; renderSettings(); };
$("fullrange").onclick = () => { draft.rstart = null; draft.rend = null; renderSettings(); };

function estimate(){
  const k = picked.length, n = draft.length;
  if (!k) return null;
  let total = permCount(k, n, RM());
  if (total === 0n) return null;
  if (draft.rstart && draft.rend && !rangeIsFull() && !rangeBad){
    const notes = ordered();
    total = rangeIndex(draft.rend, notes) - rangeIndex(draft.rstart, notes) + 1n;
  }
  const count = Number(total);   // sizes only need to be approximate
  const avg = picked.reduce((s, x) => s + x.length, 0) / k;
  const perBar = 4 + n*avg + (n-1) + 1 + 3 + 7/4;      // indent, notes, spaces, "4", " |\n", \break
  const bytes = count * perBar * 1.03 + 600;              // + chunk labels and headers
  const files = Math.max(1, Math.ceil(bytes / (draft.max_kb*1000 - 1000)));
  const txt = count * (n*avg + n);                        // notes, spaces, newline
  const txtFiles = Math.max(1, Math.ceil(txt / (draft.max_kb*1000)));
  const bps = n <= 2 ? 6 : n <= 4 ? 4 : n <= 6 ? 2 : 1;            // measures per line
  const per = s => n >= 18 ? Math.max(1, Math.floor(s / 2)) : s * bps;   // measures per page
  const mpp = per(draft.systems_per_page), first = per(draft.first_page_systems);
  const book = first + mpp * (draft.pages_per_pdf - 1);              // measures per PDF
  const bookPages = m => m <= 0 ? 0 : 1 + Math.max(0, Math.ceil((m - first) / mpp));
  const pages = Math.floor(count / book) * draft.pages_per_pdf + bookPages(count % book);
  const pdfs = Math.max(files, Math.ceil(pages / draft.pages_per_pdf));
  return {total, bytes, files, txt, txtFiles, pages, pdfs};
}

// Switching sharps <-> flats keeps the same pitches ticked (ais <-> bes, ...).
function switchSpelling(to){ respell(() => { draft.spelling = to; }); }

function renderSettings(){
  if (chipsFor !== setKey()) buildChips();
  document.querySelectorAll("#enh input").forEach(cb => { cb.checked = draft.enh.includes(cb.value); });
  document.querySelectorAll("input[name=savemode]").forEach(r => { r.checked = r.value === draft.save_mode; });
  if ($("savepath").value !== draft.save_path) $("savepath").value = draft.save_path;
  $("wtxt").checked = draft.write_txt;
  $("rm_norepeat").checked = RM() === "norepeat";
  $("rm_once").checked = RM() === "once";
  $("norepeat").checked = draft.no_repeat_acc;
  $("chunklabels").checked = draft.chunk_labels !== false;
  $("savepath").disabled = $("browse").disabled = locked || draft.save_mode !== "custom";
  $("len").value = draft.length; $("lenv").textContent = draft.length;
  $("lenwarn").hidden = draft.length <= 12;
  $("systems").value = draft.systems_per_page; $("systemsv").textContent = draft.systems_per_page;
  $("firstsys").value = draft.first_page_systems; $("firstsysv").textContent = draft.first_page_systems;
  const tooMany = (el, wanted, fit, where) => {
    $(el).hidden = wanted <= fit;
    $(el).textContent = "Warning! At staff size " + draft.staff_size + ", only about " + fit +
      " system" + (fit > 1 ? "s" : "") + " fit on " + where + ". With more, LilyPond moves the extra " +
      "lines onto added pages, so PDFs come out longer than the pages-per-PDF setting. (Estimate.)";
  };
  tooMany("firstsyswarn", draft.first_page_systems, maxSystemsPerPage(true), "a first page with the title");
  tooMany("syswarn", draft.systems_per_page, maxSystemsPerPage(false), "a letter page");
  if (document.activeElement !== $("ppdf")) $("ppdf").value = draft.pages_per_pdf;
  $("ppdf").disabled = locked;
  if ($("textfont").value !== draft.text_font) $("textfont").value = draft.text_font;
  if ($("musicfont").value !== draft.music_font) $("musicfont").value = draft.music_font;
  $("textfont").disabled = $("musicfont").disabled = locked;
  renderFontStatus();
  $("staff").value = draft.staff_size;
  $("staffv").textContent = draft.staff_size + (draft.staff_size === 20 ? " (default)" : "");
  $("kb").value = draft.max_kb; $("kbv").textContent = draft.max_kb.toLocaleString() + " KB";
  document.querySelectorAll("#chips input").forEach(cb => {
    cb.checked = picked.includes(cb.value);
  });
  document.querySelectorAll("#spellings input").forEach(r => { r.checked = r.value === draft.spelling; });
  document.querySelectorAll("#clefs input").forEach(r => { r.checked = r.value === draft.clef; });
  document.querySelectorAll("#pitches input").forEach(r => { r.checked = r.value === draft.pitch; });
  document.querySelectorAll("#lpversions input").forEach(r => { r.checked = r.value === draft.lilypond; });
  document.querySelectorAll("#pdflinks input").forEach(r => { r.checked = r.value === draft.pdf_links; });
  document.querySelectorAll("#placements input").forEach(r => { r.checked = r.value === draft.placement; });
  $("placehint").textContent = draft.placement === "nearest"
    ? "each bar starts in the chosen octave, then each note goes to the closest one"
    : "every note in the chosen octave";
  $("pickcount").textContent = picked.length + " ticked";
  $("pickall").disabled = locked || picked.length === ALL.length;
  $("picknone").disabled = locked || picked.length === 0;
  renderRange();
  $("settings").disabled = locked;
  $("fullrange").disabled = locked;
  const e = estimate(), s = $("summary");
  if (!e){ s.className = "summary"; s.textContent = picked.length ? noPermReason() : "Tick at least one note."; }
  else {
    s.className = "summary" + (e.bytes > 5e9 ? " big" : "");
    s.textContent = e.total.toLocaleString() + " permutations · about " + e.pages.toLocaleString() +
      " page" + (e.pages > 1 ? "s" : "") + " in " + e.pdfs.toLocaleString() + " PDF" + (e.pdfs > 1 ? "s" : "") +
      " · about " + fmtBytes(e.bytes) +
      " · " + e.files.toLocaleString() + " file" + (e.files > 1 ? "s" : "") +
      (draft.write_txt ? " · text about " + fmtBytes(e.txt) + " in " + e.txtFiles.toLocaleString() +
                         " file" + (e.txtFiles > 1 ? "s" : "") : "") +
      (e.bytes > 5e9 ? " — very large: this could take days and fill your disk." : "");
  }
  renderDisk(e);
  renderSteps();
  $("lock").textContent = locked
    ? (status === "stopped" ? "Settings belong to the saved run. Press Reset to change them."
                            : "Settings are locked while a run is in progress.")
    : "";
}

$("len").oninput = e => {
  draft.length = +e.target.value;
  renderSettings();
};
$("kb").oninput = e => { draft.max_kb = +e.target.value; renderSettings(); };
$("staff").oninput = e => { draft.staff_size = +e.target.value; renderSettings(); };
$("systems").oninput = e => { draft.systems_per_page = +e.target.value; renderSettings(); };
$("firstsys").oninput = e => { draft.first_page_systems = +e.target.value; renderSettings(); };
$("ppdf").oninput = e => {
  const digits = e.target.value.replace(/[^0-9]/g, "");
  if (digits !== e.target.value) e.target.value = digits;     // numbers only
  const v = parseInt(digits, 10);
  if (v > 10000){ e.target.value = "10000"; say("Pages per PDF can be at most 10,000."); }
  if (v >= 1) draft.pages_per_pdf = Math.min(v, 10000);
  renderSettings();
};
$("ppdf").onblur = () => { $("ppdf").value = draft.pages_per_pdf; };   // tidy up (empty, 0, >10,000)
$("textfont").oninput = e => { draft.text_font = e.target.value; renderFontStatus(); };
$("musicfont").oninput = e => { draft.music_font = e.target.value; renderMusicFont(); };
let musicFontsKey = "", OUTLINE_REQUIRED = [];
function outlineRequired(){ return OUTLINE_REQUIRED.includes(draft.music_font.trim().toLowerCase()); }
function renderOutline(){
  const req = outlineRequired(), cb = $("outline");
  cb.checked = req || !!draft.outline_fonts;
  cb.disabled = locked || req;                       // Cadence: on, and can't be unticked
  $("outlinelabel").classList.toggle("forced", req);
  $("outlinereq").hidden = !req;
  $("outlinewarn").hidden = !(req || draft.outline_fonts);     // the size warning only when it applies
  $("outlinereq").textContent = req ? "Required for " + draft.music_font.trim() +
    " (GPL font): its font data is never embedded in your PDFs." : "";
}
$("outline").onchange = e => {
  if (outlineRequired()){ e.target.checked = true; return; }   // can't switch it off
  draft.outline_fonts = e.target.checked;
};
function renderMusicFont(){
  renderOutline();
  const list = (LP && LP.music_fonts) || [], el = $("musicfontstat"), name = draft.music_font.trim();
  $("musicwarn").hidden = !name;      // the custom-font caution only when one is chosen
  const key = list.join(",");
  if (key !== musicFontsKey){
    musicFontsKey = key; const dl = $("musicfontlist"); dl.innerHTML = "";
    list.forEach(f => { const o = document.createElement("option"); o.value = f; dl.appendChild(o); });
  }
  el.className = "fontstat";
  if (!name){ el.textContent = list.length ? list.length + " music fonts available in LilyPond: " + list.join(", ") + "."
                                           : "Emmentaler is LilyPond's own music font."; return; }
  if (!LP || LP.error){ el.textContent = ""; return; }
  const hit = list.find(f => f.toLowerCase() === name.toLowerCase());
  if (hit){ el.className = "fontstat ok"; el.textContent = "✓ Installed in LilyPond" + (hit !== name ? " (as “" + hit + "”)" : "") + "."; }
  else { el.className = "fontstat bad"; el.textContent = "⚠ Not in LilyPond's fonts folder: LilyPond will stop with an error."; }
}

function renderFontStatus(){
  const el = $("textfontstat"), name = draft.text_font.trim();
  el.className = "fontstat";
  if (!name){ el.textContent = FONTS ? FONTS.length.toLocaleString() + " fonts found on this computer." : "Checking the fonts on this computer…"; return; }
  if (!FONTS){ el.textContent = "Checking the fonts on this computer…"; return; }
  const hit = FONTS.find(f => f.toLowerCase() === name.toLowerCase());
  if (hit){ el.className = "fontstat ok"; el.textContent = "✓ Installed" + (hit !== name ? " (as “" + hit + "”)" : "") + "."; }
  else { el.className = "fontstat bad"; el.textContent = "⚠ Not found among this computer's fonts — LilyPond would fall back to its default."; }
}
async function loadFonts(){
  try {
    const r = await (await fetch("/fonts")).json();
    FONTS = r.fonts; FONT_SOURCE = r.source;
    const dl = $("fontlist"); dl.innerHTML = "";
    FONTS.forEach(f => { const o = document.createElement("option"); o.value = f; dl.appendChild(o); });
  } catch(e){ FONTS = []; }
  renderFontStatus();
}
document.querySelectorAll("input[name=savemode]").forEach(r => {
  r.onchange = () => { draft.save_mode = r.value; renderSettings();
                       if (r.value === "custom" && !draft.save_path) $("savepath").focus(); };
});
$("savepath").oninput = e => { draft.save_path = e.target.value; };
$("norepeat").onchange = e => { draft.no_repeat_acc = e.target.checked; renderSettings(); };
$("chunklabels").onchange = e => { draft.chunk_labels = e.target.checked; renderSettings(); };
$("wtxt").onchange = e => { draft.write_txt = e.target.checked; renderSettings(); };
$("browse").onclick = async () => {
  $("browse").disabled = true; say("A folder picker is open on your computer…");
  try {
    const r = await (await fetch("/browse", {method: "POST"})).json();
    if (r.error) say(r.error);
    else { if (r.path) draft.save_path = r.path; noteUntil = 0; }
  } finally { renderSettings(); }
};

function render(d){
  status = d.status;
  if (!SETS){
    INIT = d;
    SETS = d.note_sets; ENH = d.enharmonics; buildEnh();
    $("scriptdir").textContent = d.script_dir;
    if (d.default_place) $("defaultplace").textContent = d.default_place;
    buildSeg("spellings", "spelling", Object.entries(d.spellings).map(([v, l]) => [v, l, false]),
             switchSpelling);
    buildSeg("clefs", "clef", Object.entries(d.clefs).map(([v, l]) => [v, l, false]));
    buildSeg("pitches", "pitch", d.pitches.map(p => [p, p, true]));
    buildSeg("lpversions", "lilypond", Object.entries(d.lilypond_versions).map(([v, l]) => [v, l, false]));
    buildSeg("pdflinks", "pdf_links", Object.entries(d.pdf_links).map(([v, l]) => [v, l, false]));
    buildSeg("placements", "placement", Object.entries(d.placements).map(([v, l]) => [v, l, false]));
    $("len").min = d.limits.min_len; $("len").max = d.limits.max_len;
    $("kb").min = d.limits.min_kb; $("kb").max = d.limits.max_kb;
    $("staff").min = d.limits.min_staff; $("staff").max = d.limits.max_staff;
    $("systems").min = $("firstsys").min = d.limits.min_systems;
    $("systems").max = $("firstsys").max = d.limits.max_systems;
    $("musicwarn").textContent = d.music_font_warning;
    $("outlinewarn").textContent = d.outline_warning;
    OUTLINE_REQUIRED = d.outline_required || [];
    loadFonts(); loadPresets();
  }
  const wasLocked = locked; locked = d.locked;
  if (!draft || locked || wasLocked){
    draft = {length: d.settings.length, max_kb: d.settings.max_kb,
             staff_size: d.settings.staff_size || 20,
             systems_per_page: d.settings.systems_per_page || 12,
             first_page_systems: d.settings.first_page_systems || d.settings.systems_per_page || 10,
             pages_per_pdf: d.settings.pages_per_pdf || 100,
             text_font: d.settings.text_font || "", music_font: d.settings.music_font || "",
             spelling: d.settings.spelling || "sharps",
             enh: (d.settings.enharmonics || []).slice(),
             save_mode: d.settings.save_to ? "custom" : "default",
             write_txt: !!d.settings.write_txt,
             rstart: d.settings.range_start ? d.settings.range_start.slice() : null,
             rend: d.settings.range_end ? d.settings.range_end.slice() : null,
             save_path: d.settings.save_to || (draft ? draft.save_path : ""),
             clef: d.settings.clef, pitch: d.settings.pitch,
             placement: d.settings.placement || "fixed",
             no_repeat_acc: !!d.settings.no_repeat_acc,
             chunk_labels: d.settings.chunk_labels !== false,
             lilypond: d.settings.lilypond || "2.26",
             repeat_mode: d.settings.repeat_mode || "all",
             pdf_links: d.settings.pdf_links || "off",
             outline_fonts: !!d.settings.outline_fonts};
    picked = d.settings.notes.slice();
  }
  renderSettings();
  renderLilypond(d);
  renderMusicFont();
  renderEngrave(d);
  renderWindowNote(d);

  $("pill").textContent = d.status; $("pill").className = "pill " + d.status;
  $("fill").style.width = d.percent + "%";
  $("pct").textContent = d.percent.toFixed(1) + "%";
  const est = estimate();
  const total = (d.status === "idle" && est) ? est.total.toLocaleString() : d.total_text;  // preview before Start
  $("count").textContent = d.done_text + " / " + total;
  $("elapsed").textContent = fmtTime(d.elapsed);
  $("chunk").textContent = d.chunk;
  $("nfiles").textContent = d.file_total;
  $("msg").textContent = Date.now() < noteUntil ? note : d.message;
  $("recent").textContent = d.recent.join("\n");
  $("outdir").textContent = d.out_dir;
  // the list is rebuilt only when it changes, keeping its scroll position (rebuilding it on
  // every status update kept pulling the scroll bar back to the top)
  const filesKey = JSON.stringify([d.files, d.current_file]);
  if (filesKey !== lastFilesKey){
    lastFilesKey = filesKey;
    const f = $("files");
    if (!d.files.length && !d.current_file) f.innerHTML = '<span class="empty">None yet.</span>';
    else {
      let ul = f.querySelector("ul");
      const top = ul ? ul.scrollTop : 0;
      const atEnd = ul ? ul.scrollTop + ul.clientHeight >= ul.scrollHeight - 4 : false;
      if (!ul){ f.innerHTML = ""; ul = document.createElement("ul"); f.appendChild(ul); }
      const items = d.files.slice();
      if (d.current_file) items.push(d.current_file + "  (writing)");
      ul.replaceChildren(...items.map(n => { const li = document.createElement("li"); li.textContent = n; return li; }));
      ul.scrollTop = atEnd ? ul.scrollHeight : top;   // following the end? keep following it
    }
  }
  const s = d.status;
  $("start").textContent = (s === "paused" || s === "stopped") ? "Resume"
                         : (s === "done" ? "Start new run" : "Start");
  $("start").disabled = (s === "running") || (!locked && rangeBad);
  $("pause").disabled = (s !== "running");
  $("stop").disabled = !(s === "running" || s === "paused");
  $("reset").disabled = (s === "running" || s === "paused");
}

let lastFilesKey = "";
async function poll(){
  try { render(await (await fetch("/status")).json()); }
  catch(e){ $("msg").textContent = "Lost contact with the program. Is it still running?"; }
}
async function send(action, body){
  noteUntil = 0;   // a new action replaces any earlier warning
  const r = await fetch("/" + action, {method: "POST", headers: {"Content-Type": "application/json"},
                                      body: JSON.stringify(body || {})});
  render(await r.json());
}
$("start").onclick = () => {
  if (status === "paused" || status === "stopped") return send("start");
  const e = estimate();
  if (!e){ say(picked.length ? noPermReason() : "Tick at least one note."); return; }
  const tf = draft.text_font.trim();
  if (tf && FONTS && FONTS.length && !FONTS.some(f => f.toLowerCase() === tf.toLowerCase()) &&
      !confirm("“" + tf + "” wasn't found among this computer's fonts. Use it anyway?")) return;
  if (draft.music_font.trim() && !confirm("Music font “" + draft.music_font.trim() + "”: " +
      $("musicwarn").textContent)) return;
  if (rangeBad){ say(rangeComplete() ? $("rangewarn").textContent
                                     : "Finish the range: every box needs one of the ticked notes."); return; }
  if (!$("diskwarn").hidden && !confirm($("diskwarn").textContent + " Start anyway?")) return;
  if (draft.save_mode === "custom" && !draft.save_path.trim()){
    say("Type or browse to a save folder, or choose “" + $("defaultplace").textContent + "”."); return; }
  if (e.bytes > 5e9 && !confirm("This run is about " + fmtBytes(e.bytes) + ". Start anyway?")) return;
  send("start", startBody());
};
function startBody(){
  if (!estimate()){ say(picked.length ? noPermReason() : "Tick at least one note."); return null; }
  if (rangeBad){ say(rangeComplete() ? $("rangewarn").textContent
                                     : "Finish the range: every box needs one of the ticked notes."); return null; }
  return {length: draft.length, notes: ordered(), max_kb: draft.max_kb,
                 staff_size: draft.staff_size, systems_per_page: draft.systems_per_page,
                 first_page_systems: draft.first_page_systems,
                 pages_per_pdf: draft.pages_per_pdf,
                 text_font: draft.text_font.trim(), music_font: draft.music_font.trim(),
                 spelling: draft.spelling, enharmonics: draft.enh, clef: draft.clef, pitch: draft.pitch,
                 placement: draft.placement, lilypond: draft.lilypond,
                 no_repeat_acc: draft.no_repeat_acc, repeat_mode: RM(), pdf_links: draft.pdf_links,
                 chunk_labels: draft.chunk_labels !== false,
                 outline_fonts: !!draft.outline_fonts || outlineRequired(),
                 save_to: draft.save_mode === "custom" ? draft.save_path : "",
                 write_txt: draft.write_txt,
                 range_start: rangeIsFull() ? null : draft.rstart,
                 range_end: rangeIsFull() ? null : draft.rend};
}
$("pause").onclick = () => send("pause");
$("stop").onclick = () => send("stop");
$("reset").onclick = () => {
  if (confirm("Forget the saved progress so you can change settings?")) send("reset");
};
poll(); const pollTimer = setInterval(poll, 250);
</script></body></html>
"""

engine = None   # created in main()


def pick_folder(result_file):
    """Runs in a second copy of this program: shows the system folder picker and
    writes the chosen path to result_file."""
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)   # keep the dialog in front of the browser
        root.lift()
        root.focus_force()
    except Exception:
        pass
    path = filedialog.askdirectory(title="Choose where to save the scores", parent=root) or ""
    with open(result_file, "w", encoding="utf-8") as f:
        f.write(path)


# ---------------- installed fonts ----------------
_font_cache = None
_font_lock = threading.Lock()


def _font_dirs():
    home = os.path.expanduser("~")
    if sys.platform.startswith("win"):
        windir = os.environ.get("WINDIR", r"C:\Windows")
        local = os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
        return [os.path.join(windir, "Fonts"), os.path.join(local, "Microsoft", "Windows", "Fonts")]
    if sys.platform == "darwin":
        return ["/System/Library/Fonts", "/Library/Fonts", os.path.join(home, "Library", "Fonts")]
    return ["/usr/share/fonts", "/usr/local/share/fonts",
            os.path.join(home, ".fonts"), os.path.join(home, ".local", "share", "fonts")]


def _family_names(path):
    """Family names inside a .ttf/.otf/.ttc/.otc file (from its 'name' table)."""
    names = set()
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return names
    offsets = [0]
    if data[:4] == b"ttcf":
        n = struct.unpack(">I", data[8:12])[0]
        offsets = list(struct.unpack(f">{n}I", data[12:12 + 4 * n]))
    for base in offsets:
        try:
            num_tables = struct.unpack(">H", data[base + 4:base + 6])[0]
            for t in range(num_tables):
                rec = base + 12 + 16 * t
                tag = data[rec:rec + 4]
                if tag != b"name":
                    continue
                off = struct.unpack(">I", data[rec + 8:rec + 12])[0]
                _, count, str_off = struct.unpack(">HHH", data[off:off + 6])
                found = {}
                for k in range(count):
                    r = off + 6 + 12 * k
                    pid, eid, lid, nid, ln, so = struct.unpack(">HHHHHH", data[r:r + 12])
                    if nid not in (1, 16):
                        continue
                    raw = data[off + str_off + so: off + str_off + so + ln]
                    if pid == 3 or pid == 0:
                        txt = raw.decode("utf-16-be", "ignore")
                        english = pid == 0 or lid == 0x409
                    elif pid == 1:
                        txt = raw.decode("mac_roman", "ignore")
                        english = lid == 0
                    else:
                        continue
                    if txt and (english or nid not in found):
                        found[nid] = txt.strip()
                # the typographic family (16) when present, else the family (1)
                fam = found.get(16) or found.get(1)
                if fam:
                    names.add(fam)
        except (struct.error, IndexError):
            continue
    return names


def _fonts_from_lilypond():
    lp = find_lilypond().get("path") or shutil.which("lilypond")   # bundled LilyPond first
    if not lp:
        return set()
    try:
        r = subprocess.run([lp, "-dshow-available-fonts"], capture_output=True,
                           text=True, errors="replace", timeout=120, creationflags=NO_WINDOW)
    except Exception:
        return set()
    fams = set()
    for line in (r.stdout + "\n" + r.stderr).splitlines():
        # "family Name" (2.24+) or "family 12: Name" (older versions)
        m = re.match(r"\s*family\s+(?:\d+\s*:\s*)?(.+?)\s*$", line)
        if m:
            name = m.group(1)
            # skip LilyPond's music-font sizes (emmentaler-20, profondo-brace, ...)
            if not re.search(r"-(\d+|brace)$", name, re.IGNORECASE):
                fams.add(name)
    return fams


def installed_fonts():
    """Font family names on this computer. Asks LilyPond itself when it is on the
    PATH (its list is exactly what it can use); otherwise reads the font files."""
    global _font_cache
    with _font_lock:
        if _font_cache is None:
            fams, source = _fonts_from_lilypond(), "LilyPond"
            if not fams:
                source = "this computer's font folders"
                for d in _font_dirs():
                    for root, _, files in os.walk(d):
                        for name in files:
                            if name.lower().endswith((".ttf", ".otf", ".ttc", ".otc")):
                                fams |= _family_names(os.path.join(root, name))
            _font_cache = {"fonts": sorted(fams, key=str.lower), "source": source}
        return _font_cache


def disk_free(path):
    """Free bytes on the drive holding path (or its nearest existing parent)."""
    p = os.path.abspath(os.path.expanduser(path or DATA_DIR))
    while not os.path.exists(p) and os.path.dirname(p) != p:
        p = os.path.dirname(p)
    try:
        return {"free": shutil.disk_usage(p).free, "path": p}
    except OSError as e:
        return {"error": str(e)}


# ---------------- LilyPond: finding it, previewing, engraving ----------------
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")   # app settings (e.g. LilyPond path)


def load_config():
    try:
        with open(CONFIG_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, CONFIG_FILE)


NO_WINDOW = 0x08000000 if os.name == "nt" else 0   # Windows: no console window pops up


def lilypond_candidates():
    """(where it came from, path) for every place LilyPond might be, best first."""
    exe = "lilypond.exe" if os.name == "nt" else "lilypond"
    cands = []
    own = load_config().get("lilypond_path")
    if own:
        cands.append(("your setting", own))
    for base in dict.fromkeys((BUNDLE_RESOURCES, RESOURCE_DIR, SCRIPT_DIR)):   # bundled with the app
        for pat in ("lilypond/bin", "lilypond/*/bin", "lilypond-*/bin"):
            for d in sorted(glob.glob(os.path.join(base, pat)), reverse=True):
                cands.append(("bundled", os.path.join(d, exe)))
    found = shutil.which("lilypond")
    if found:
        cands.append(("installed", found))
    home = os.path.expanduser("~")
    if os.name == "nt":
        pats = [os.path.join(os.environ.get(v, ""), "lilypond-*", "bin", exe)
                for v in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA") if os.environ.get(v)]
        pats.append(os.path.join(home, "lilypond-*", "bin", exe))
    else:
        pats = [os.path.join(home, "lilypond-*", "bin", exe), "/Applications/lilypond-*/bin/lilypond",
                "/Applications/LilyPond*.app/Contents/Resources/bin/lilypond",
                "/opt/homebrew/bin/lilypond", "/usr/local/bin/lilypond", "/usr/bin/lilypond"]
    for pat in pats:
        for p in sorted(glob.glob(pat), reverse=True):
            cands.append(("installed", p))
    return cands


_lp_lock = threading.Lock()
_lp_info = None


def find_lilypond(refresh=False):
    """{'path', 'version', 'source'} for the first working LilyPond, or {'error'}."""
    global _lp_info
    with _lp_lock:
        if _lp_info is not None and not refresh:
            return _lp_info
        info, tried = None, []
        for source, path in lilypond_candidates():
            if not os.path.isfile(path):
                if source == "your setting":
                    tried.append(f"{path} (not found)")
                continue
            try:
                r = subprocess.run([path, "--version"], capture_output=True, text=True,
                                   timeout=60, creationflags=NO_WINDOW)
                m = re.search(r"GNU LilyPond (\d+\.\d+\.\d+)", r.stdout + r.stderr)
            except Exception as e:
                tried.append(f"{path} ({e})")
                continue
            if m:
                info = {"path": os.path.abspath(path), "version": m.group(1), "source": source,
                        "music_fonts": lilypond_music_fonts(path)}
                break
            tried.append(f"{path} (didn't report a LilyPond version)")
        _lp_info = info or {"error": "LilyPond wasn't found." + (" Tried: " + "; ".join(tried) if tried else "")}
        return _lp_info


MUSIC_FONT_SIZES = (11, 13, 14, 16, 18, 20, 23, 26)


def lilypond_music_fonts(path):
    """Music fonts installed in this LilyPond (complete sets of -11 ... -26 .otf files)."""
    names = set()
    for d in glob.glob(os.path.join(lilypond_root(path), "share", "lilypond", "*", "fonts", "otf")):
        for f in os.listdir(d):
            m = re.match(r"^(.+)-20\.otf$", f)
            if m and m.group(1) != "emmentaler" and all(
                    os.path.exists(os.path.join(d, f"{m.group(1)}-{z}.otf")) for z in MUSIC_FONT_SIZES):
                names.add(m.group(1))
    return sorted(names)


def lilypond_root(path):
    """.../lilypond-2.26.0/bin/lilypond -> .../lilypond-2.26.0"""
    return os.path.dirname(os.path.dirname(os.path.realpath(path)))


PREVIEW_DIR = os.path.join(tempfile.gettempdir(), "melodarium-preview")
_preview_lock = threading.Lock()


def make_preview(raw):
    """Engrave the first page of the current settings into PREVIEW_DIR/preview.pdf."""
    settings, err = validate(raw)
    if err:
        return {"ok": False, "error": err}
    lp = find_lilypond()
    if not lp.get("path"):
        return {"ok": False, "error": lp.get("error", "LilyPond wasn't found.")}
    plan = Plan(settings)
    with _preview_lock:
        shutil.rmtree(PREVIEW_DIR, ignore_errors=True)
        os.makedirs(PREVIEW_DIR, exist_ok=True)
        with open(os.path.join(PREVIEW_DIR, CC0_EPS_NAME), "w") as f:
            f.write(CC0_EPS)
        last = min(plan.last, plan.first + plan.first_page_measures - 1)
        with open(os.path.join(PREVIEW_DIR, "preview.ly"), "w") as f:
            f.write(plan.whole_file(plan.first, last, 1, "preview"))
        try:
            r = subprocess.run([lp["path"], "preview.ly"], cwd=PREVIEW_DIR, capture_output=True,
                               text=True, errors="replace", timeout=300, creationflags=NO_WINDOW)
            log = r.stdout + r.stderr
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "LilyPond took too long (over 5 minutes)."}
        notes = [l.strip() for l in log.splitlines() if re.search(r"(warning|error):", l)]
        ok = r.returncode == 0 and os.path.exists(os.path.join(PREVIEW_DIR, "preview.pdf"))
        if ok and plan.outline_fonts and music_font_embedded(os.path.join(PREVIEW_DIR, "preview.pdf"),
                                                             plan.music_font):
            notes.insert(0, "Output to outline didn't take effect: the music font is embedded in this PDF.")
        return {"ok": ok, "warnings": notes[:20],
                "error": None if ok else "LilyPond reported a problem:\n" + "\n".join(log.splitlines()[-15:])}


def explain_lilypond_failure(log, code):
    """Plain-English reasons for a failed engraving, from LilyPond's output."""
    reasons, seen = [], set()

    def add(text):
        if text not in seen:
            seen.add(text)
            reasons.append(text)
    for line in log.splitlines():
        m = re.search(r"cannot rename .* to [`'\"]?([^`'\"]+\.pdf)", line)
        if m:
            add(f"Couldn't save {m.group(1)}: it is probably open in a PDF viewer or browser "
                "(Windows can't replace an open file). Close it and press Engrave PDFs again.")
            continue
        if re.search(r"bad_alloc|out of memory|memory exhausted|cannot allocate", line, re.I):
            add("LilyPond ran out of memory. Lower \"Pages per PDF\" (or the file size) and run again.")
            continue
        m = re.search(r"cannot find font [`'\"]?([^`'\" ]+)", line)
        if m:
            add(f"The music font {m.group(1)} isn't installed in LilyPond's fonts folder.")
            continue
        if re.search(r"cannot (open|write)|Permission denied|No space left", line, re.I):
            add("LilyPond couldn't write to the folder (no permission, or the disk is full): " + line.strip())
            continue
        if "Output to outline didn't take effect" in line:
            add(line.strip())
            continue
        if re.search(r"\b(fatal error|error|programming error):", line):
            add("LilyPond reported: " + line.strip())
    if not reasons:
        if not log.strip():
            add(f"LilyPond stopped without any message (exit code {code}). It may have been closed by "
                "antivirus software or run out of memory.")
        else:
            add(f"LilyPond stopped with exit code {code} without naming an error; see the full log.")
    return reasons


class Engraver:
    """Engraves a run's score files one at a time (one LilyPond process each)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.proc = None
        self.stop_flag = False
        self.status = "idle"            # idle | running | done | stopped
        self.folder = ""
        self.current = ""
        self.done = self.total = self.skipped = 0
        self.failed = []                # [{"file", "log"}]
        self.started = 0.0

    @staticmethod
    def up_to_date(path):
        """True if every PDF this score file makes exists and is newer than the file."""
        try:
            with open(path, encoding="ascii", errors="replace") as f:
                names = re.findall(r'\\bookOutputName "([^"]+)"', f.read())
            mtime = os.path.getmtime(path)
        except OSError:
            return False
        folder = os.path.dirname(path)
        return bool(names) and all(
            os.path.exists(os.path.join(folder, n + ".pdf"))
            and os.path.getmtime(os.path.join(folder, n + ".pdf")) >= mtime for n in names)

    @staticmethod
    def outline_failures(path):
        """For a score file set to output music to outline: PDFs that still embed the music font (deleted)."""
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            return []
        mark = re.search(OUTLINE_MARK_RE, text)
        if not mark:
            return []
        bad = []
        for n in re.findall(r'\\bookOutputName "([^"]+)"', text):
            pdf = os.path.join(os.path.dirname(path), n + ".pdf")
            if music_font_embedded(pdf, mark.group(1)):
                bad.append(n + ".pdf")
                try:
                    os.remove(pdf)
                except OSError:
                    pass
        return bad

    def start(self, folder, files, lilypond):
        with self.lock:
            if self.status == "running":
                return
            self.status, self.folder, self.stop_flag = "running", folder, False
            self.current, self.done, self.total, self.skipped = "", 0, len(files), 0
            self.failed, self.started = [], time.time()
        threading.Thread(target=self._run, args=(folder, list(files), lilypond), daemon=True).start()

    def stop(self):
        with self.lock:
            self.stop_flag = True
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()

    def _run(self, folder, files, lilypond):
        for name in files:
            if self.stop_flag:
                break
            path = os.path.join(folder, name)
            if self.up_to_date(path):
                with self.lock:
                    self.done += 1
                    self.skipped += 1
                continue
            with self.lock:
                self.current = name
                try:
                    self.proc = subprocess.Popen([lilypond, name], cwd=folder, stdout=subprocess.PIPE,
                                                 stderr=subprocess.STDOUT, text=True, errors="replace",
                                                 creationflags=NO_WINDOW)
                except OSError as e:
                    self.failed.append({"file": name, "reasons": [f"LilyPond couldn't be started: {e}"],
                                        "code": None, "log": "", "logfile": ""})
                    self.done += 1
                    continue
            out = self.proc.communicate()[0]
            if self.proc.returncode == 0 and not self.stop_flag:
                bad = self.outline_failures(path)
                if bad:
                    out += ("\nOutput to outline didn't take effect: the music font is embedded in "
                            + ", ".join(bad) + ". These PDFs were deleted.")
                    self.proc.returncode = 1
            with self.lock:
                if self.proc.returncode != 0 and not self.stop_flag:
                    # keep LilyPond's whole output next to the score file for reference
                    logfile = os.path.splitext(name)[0] + ".log"
                    try:
                        with open(os.path.join(folder, logfile), "w", encoding="utf-8") as f:
                            f.write(out)
                    except OSError:
                        logfile = ""
                    lines = [l for l in out.splitlines() if not re.match(r"^(Interpreting music|Preprocessing|"
                             r"Calculating|Drawing|Fitting|Finding|Processing|Parsing|Converting|Layout)", l)]
                    self.failed.append({"file": name, "code": self.proc.returncode, "logfile": logfile,
                                        "reasons": explain_lilypond_failure(out, self.proc.returncode),
                                        "log": "\n".join(lines[-6:])})
                if not self.stop_flag:
                    self.done += 1
                self.proc = None
        with self.lock:
            self.status = "stopped" if self.stop_flag else "done"
            self.current = ""

    def snapshot(self):
        with self.lock:
            return {"status": self.status, "done": self.done, "total": self.total,
                    "skipped": self.skipped, "current": self.current, "failed": self.failed[-5:],
                    "failed_count": len(self.failed), "elapsed": time.time() - self.started if self.started else 0}


engraver = Engraver()


# ---------------- acknowledgements ----------------
FRIENDLY = {"tg2_501otf": "TeX Gyre fonts (2.501)", "urw-base35-fonts": "URW base 35 fonts",
            "gc": "Boehm–Demers–Weiser garbage collector", "Python": "Python (used by LilyPond's tools)"}


def app_licenses_dir():
    for base in dict.fromkeys((RESOURCE_DIR, BUNDLE_RESOURCES, SCRIPT_DIR)):
        d = os.path.join(base, "licenses")
        if os.path.isdir(d):
            return d
    return None


def license_dirs():
    """Folders the acknowledgements page may show license files from."""
    dirs = {}
    a = app_licenses_dir()
    if a:
        dirs["app"] = a
    lp = find_lilypond()
    if lp.get("path") and os.path.isdir(os.path.join(lilypond_root(lp["path"]), "licenses")):
        dirs["lilypond"] = os.path.join(lilypond_root(lp["path"]), "licenses")
    return dirs


def read_license(src, rel):
    """Text of one license file, only from the known license folders."""
    base = license_dirs().get(src)
    if not base:
        return None
    path = os.path.realpath(os.path.join(base, rel))
    if not path.startswith(os.path.realpath(base) + os.sep) or not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def font_license_summary(text):
    """(license name, copyright notice) for a bundled font's license file."""
    if "Open Font License" in text:
        return ("SIL Open Font License, Version 1.1",
                text.split("This Font Software is licensed")[0].strip())
    if "GNU General Public License" in text:
        later = "any later version" in text
        ver = re.search(r"either version (\d)", text) or re.search(r"Version (\d), ", text)
        lic = "GNU General Public License" + (f", version {ver.group(1)}" if ver else "") + (" or later" if later else "")
        notice = " ".join(l.strip() for l in text.split("This program is free software")[0].splitlines()
                          if l.strip())
        return lic, notice
    if "UNRESTRICTED" in text:
        who = re.search(r"I, ([^,]+),\s+hereby\s+disclaim", text)
        return ("Unrestricted use (copyright disclaimed)",
                (f"Font files: {who.group(1)} disclaims all copyright; anyone may use, copy, modify and "
                 "redistribute them with no conditions. " if who else "")
                + ("Source code: MIT license." if "Permission is hereby granted, free of charge" in text else ""))
    return "see license", ""


def acknowledgements_html(theme=None):
    """The acknowledgements page; theme "light"/"dark" matches the panel's choice."""
    from html import escape as esc
    theme_attr = f" data-theme='{theme}'" if theme in ("light", "dark") else ""
    dirs, lp = license_dirs(), find_lilypond()
    link = lambda src, rel, label=None: (f'<a href="/license?src={src}&amp;f={esc(rel)}" target="_blank">'
                                         f'{esc(label or os.path.basename(rel))}</a>')
    out = [f"<!doctype html><html lang='en'{theme_attr}><head><meta charset='utf-8'>",
           "<meta name='viewport' content='width=device-width, initial-scale=1'><title>Acknowledgements</title><style>",
           ":root{--bg:#f6f5f2;--card:#fff;--ink:#1d1d1f;--muted:#6b6b70;--line:#e3e1dc;--accent:#2f6f5e}",
           "@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#151517;--card:#1f1f22;--ink:#ececee;--muted:#9a9aa1;--line:#2e2e33;--accent:#5fb39b}}",
           ":root[data-theme=dark]{--bg:#151517;--card:#1f1f22;--ink:#ececee;--muted:#9a9aa1;--line:#2e2e33;--accent:#5fb39b}",
           "body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}",
           "main{max-width:760px;margin:0 auto;padding:28px 16px 48px}h1{font-size:24px;margin:0 0 6px}",
           "h2{font-size:15px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:28px 0 10px}",
           ".item{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-bottom:8px}",
           ".item b{font-size:15px}.small{color:var(--muted);font-size:13px}a{color:var(--accent)}",
           "pre{white-space:pre-wrap;font-size:12px;background:var(--bg);padding:10px;border-radius:6px;max-height:320px;overflow:auto}",
           "</style></head><body><main>",
           "<h1>Acknowledgements</h1>",
           "<p class='small'>Melodarium is built with, and includes, the free software and fonts below, "
           "used under their licenses. Click a license name to read it in full.</p>"]

    # ---- the scores ----
    out.append("<h2>Your scores</h2><div class='item'><b>CC0 1.0 Universal</b> — the scores carry a "
               "<a href='https://creativecommons.org/publicdomain/zero/1.0/' target='_blank'>CC0 public domain dedication</a>."
               "<div class='small'>The CC0 badge printed on each page is a trademark of Creative Commons, used under the "
               "<a href='https://creativecommons.org/policies' target='_blank'>Creative Commons trademark policy</a> "
               "with a link to the CC0 deed. It comes from Creative Commons' "
               "<a href='https://github.com/creativecommons/vocabulary' target='_blank'>vocabulary</a> design system "
               "(80×15 badge), converted from SVG to EPS without changing the design.</div></div>")

    # ---- music fonts ----
    out.append("<h2>Music fonts</h2>")
    fonts = []
    if dirs.get("app") and os.path.isdir(os.path.join(dirs["app"], "fonts")):
        for name in sorted(os.listdir(os.path.join(dirs["app"], "fonts")), key=str.lower):
            fdir = os.path.join(dirs["app"], "fonts", name)
            files = sorted(f for f in os.listdir(fdir) if os.path.isfile(os.path.join(fdir, f))) if os.path.isdir(fdir) else []
            if files:
                fonts.append((name, files))
    for name, files in fonts:
        includes = read_license("app", f"fonts/{name}/INCLUDES.txt") if "INCLUDES.txt" in files else ""
        files = [f for f in files if f != "INCLUDES.txt"]
        main = next((f for f in files if f.lower().startswith(("ofl", "license", "licence"))), files[0])
        text = read_license("app", f"fonts/{name}/{main}") or ""
        lic, notice = font_license_summary(text)
        if name.lower() in OUTLINE_REQUIRED:
            notice += ("\nUsed only with “output music to outline”: the music symbols are drawn as shapes, "
                       "so no font data from it is embedded in your PDFs.")
        rfn = re.search(r'Reserved Font Names?\s+"?([^"\n.]+)"?', text)
        title = rfn.group(1).strip() if rfn else name.capitalize()
        out.append(f"<div class='item'><b>{esc(title)}</b> <span class='small'>({esc(name)})</span> — {esc(lic)}"
                   + "".join(f"<div class='small'>{esc(line)}</div>" for line in notice.split("\n") if line)
                   + (f"<div class='small'>{esc(includes.strip())}</div>" if includes else "")
                   + "<div class='small'>" + " · ".join(link('app', f'fonts/{name}/{f}', f) for f in files) + "</div></div>")
    out.append("<div class='item'><b>Emmentaler</b> (LilyPond's own music font) — SIL Open Font License, Version 1.1, "
               "or GPL with font exception<div class='small'>Copyright (c) 1996–2026, The LilyPond authors (lilypond.org), "
               "with Reserved Font Names “Emmentaler” and “Feta”.</div>"
               + (f"<div class='small'>{link('app', 'emmentaler/OFL.txt', 'OFL.txt')}</div>"
                  if read_license("app", "emmentaler/OFL.txt") else "") + "</div>")
    if not fonts:
        out.append("<p class='small'>No other music fonts are bundled yet.</p>")
    out.append("<p class='small'>Text fonts are not bundled: any text font you choose comes from your own "
               "computer and is used under its own license.</p>")

    # ---- LilyPond and what it includes ----
    out.append("<h2>LilyPond</h2>")
    if lp.get("path"):
        v = lp["version"]
        out.append(f"<div class='item'><b>GNU LilyPond {esc(v)}</b> — GNU General Public License, version 3 or later"
                   f"<div class='small'>Engraves the scores. Source code: "
                   f"<a href='https://lilypond.org/download/sources/v{'.'.join(v.split('.')[:2])}/lilypond-{v}.tar.gz' target='_blank'>"
                   f"lilypond-{v}.tar.gz</a> from <a href='https://lilypond.org' target='_blank'>lilypond.org</a>.</div></div>")
        if dirs.get("lilypond"):
            groups = {}
            for f in sorted(os.listdir(dirs["lilypond"]), key=str.lower):
                m = re.match(r"^(.*?)\.(?=[A-Z])", f)
                groups.setdefault(m.group(1) if m else f, []).append(f)
            out.append("<p class='small'>LilyPond's package includes these components, each under its own license "
                       "(their source code is available from each project):</p>")
            for comp, files in groups.items():
                m = re.match(r"^(.*?)-(\d[\w.]*)$", comp)
                name, ver = (m.group(1), m.group(2)) if m else (comp, "")
                label = FRIENDLY.get(name, FRIENDLY.get(comp, name))
                out.append(f"<div class='item'><b>{esc(label)}</b> {esc(ver)}<div class='small'>"
                           + " · ".join(link('lilypond', f) for f in files) + "</div></div>")
    else:
        out.append("<p class='small'>LilyPond wasn't found, so its components can't be listed here.</p>")

    # ---- the app itself ----
    out.append("<h2>This app</h2><div class='item'><b>Python</b> — Python Software Foundation License"
               "<div class='small'>The packaged app includes the Python runtime and its standard library "
               "(including Tcl/Tk for the folder picker). <a href='https://docs.python.org/3/license.html' target='_blank'>"
               "Python license</a> · <a href='https://www.tcl.tk/software/tcltk/license.html' target='_blank'>Tcl/Tk license</a></div></div>"
               "<div class='item'><b>PyInstaller</b> — GPL version 2 with a bootloader exception"
               "<div class='small'>Packages the app. Its exception allows apps it builds to use any license. "
               "<a href='https://pyinstaller.org/en/stable/license.html' target='_blank'>PyInstaller license</a></div></div>")
    out.append("</main></body></html>")
    return "\n".join(out)


PRESETS_FILE = os.path.join(DATA_DIR, "presets.json")


def load_presets():
    try:
        with open(PRESETS_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_presets(presets):
    tmp = PRESETS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(presets, f, indent=2)
    os.replace(tmp, PRESETS_FILE)


MAC_PICKER = [
    "activate",   # bring the dialog to the front, above the browser
    'set chosen to choose folder with prompt "Choose where to save the scores"',
    "return POSIX path of chosen",
]


def window_folder_dialog():
    """In the app window: the system folder picker, attached to the window. None otherwise
    (or if it fails), and the usual picker is used instead."""
    if APP_WINDOW is None:
        return None
    try:
        import webview
        kind = getattr(getattr(webview, "FileDialog", None), "FOLDER", None)
        if kind is None:
            kind = webview.FOLDER_DIALOG
        chosen = APP_WINDOW.create_file_dialog(kind)
        if not chosen:
            return {"path": ""}
        return {"path": chosen[0] if isinstance(chosen, (list, tuple)) else str(chosen)}
    except Exception:
        return None


def browse_for_folder():
    """Show the computer's own folder picker.
    Mac: the system "choose folder" dialog via AppleScript (brought to the front).
    Windows (and others): the standard folder dialog via Tk, shown by a short-lived
    second copy of this program so it is safe whether packaged or not."""
    if sys.platform == "darwin":
        cmd = ["osascript"]
        for line in MAC_PICKER:
            cmd += ["-e", line]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        except Exception:
            return {"error": "Couldn't open the folder picker. Type the path instead."}
        if r.returncode != 0:
            if "-128" in r.stderr:          # the user pressed Cancel
                return {"path": ""}
            return {"error": "Couldn't open the folder picker. Type the path instead."}
        path = r.stdout.strip()
        return {"path": path.rstrip("/") or "/"}

    import tempfile
    fd, result_file = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--pick-folder", result_file]
    else:
        cmd = [sys.executable, os.path.abspath(__file__), "--pick-folder", result_file]
    try:
        r = subprocess.run(cmd, timeout=600)
        with open(result_file, encoding="utf-8") as f:
            path = f.read().strip()
    except Exception:
        r, path = None, ""
    finally:
        try:
            os.remove(result_file)
        except OSError:
            pass
    if r is None or r.returncode != 0:
        return {"error": "Couldn't open a folder picker on this computer. Type the path instead."}
    return {"path": path}


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, ctype):
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        url = urlparse(self.path)
        if url.path == "/ping":               # lets a second launch find this one
            self._send(json.dumps({"app": APP_NAME}), "application/json")
        elif url.path == "/focus":            # a second launch: bring the app window forward
            self._send(json.dumps({"window": bring_window_to_front()}), "application/json")
        elif url.path == "/diskfree":
            path = (parse_qs(url.query).get("path") or [""])[0]
            self._send(json.dumps(disk_free(path)), "application/json")
        elif url.path == "/presets":
            self._send(json.dumps(load_presets()), "application/json")
        elif url.path == "/acknowledgements":
            self._send(acknowledgements_html((parse_qs(url.query).get("theme") or [None])[0]),
                       "text/html; charset=utf-8")
        elif url.path == "/license":
            q = parse_qs(url.query)
            text = read_license((q.get("src") or [""])[0], (q.get("f") or [""])[0])
            if text is None:
                self.send_error(404)
            else:
                self._send(text, "text/plain; charset=utf-8")
        elif url.path == "/preview.pdf":
            try:
                with open(os.path.join(PREVIEW_DIR, "preview.pdf"), "rb") as f:
                    data = f.read()
            except OSError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/":
            self._send(PAGE, "text/html; charset=utf-8")
        elif self.path == "/fonts":
            self._send(json.dumps(installed_fonts()), "application/json")
        elif self.path == "/status":
            self._send(json.dumps(engine.snapshot()), "application/json")
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            body = {}
        if self.path == "/start":
            engine.start(body)
        elif self.path == "/pause":
            engine.pause()
        elif self.path == "/stop":
            engine.stop()
        elif self.path == "/browse":
            self._send(json.dumps(window_folder_dialog() or browse_for_folder()), "application/json")
            return
        elif self.path == "/reset":
            engine.reset()
        elif self.path == "/presets":          # save {"name", "preset"}
            name = str(body.get("name", "")).strip()[:60]
            presets = load_presets()
            if name and isinstance(body.get("preset"), dict):
                presets[name] = body["preset"]
                save_presets(presets)
            self._send(json.dumps(presets), "application/json")
            return
        elif self.path == "/presets/delete":   # {"name"}
            presets = load_presets()
            presets.pop(str(body.get("name", "")), None)
            save_presets(presets)
            self._send(json.dumps(presets), "application/json")
            return
        elif self.path == "/lilypond":          # {"path": ""} = find it automatically
            cfg = load_config()
            cfg["lilypond_path"] = str(body.get("path", "")).strip().strip('"')
            save_config(cfg)
            self._send(json.dumps(find_lilypond(refresh=True)), "application/json")
            return
        elif self.path == "/preview":
            self._send(json.dumps(make_preview(body)), "application/json")
            return
        elif self.path == "/engrave":
            lp = find_lilypond()
            snap = engine.snapshot()
            if lp.get("path") and snap["status"] != "running":
                engraver.start(engine.plan.out_dir, list(engine.state.get("files", [])), lp["path"])
        elif self.path == "/engrave/stop":
            engraver.stop()
        elif self.path == "/quit":
            engraver.stop()
            engine.stop()                      # saves progress
            self._send(json.dumps({"ok": True}), "application/json")
            if APP_WINDOW is not None:           # the app window: close it; main() then ends
                threading.Timer(0.3, lambda: APP_WINDOW and APP_WINDOW.destroy()).start()
            else:
                threading.Thread(target=SERVER.shutdown, daemon=True).start()
            return
        else:
            self.send_error(404)
            return
        self._send(json.dumps(engine.snapshot()), "application/json")

    def log_message(self, *args):  # keep the terminal quiet
        pass


SERVER = None


# ---------------- the app window (pywebview) ----------------
# The panel opens in its own app window when it can; otherwise in the web browser.
#  1. Windows: Microsoft's documented registry check for the WebView2 Runtime.
#  2. WebView2 present (always on a Mac) and pywebview importable: open the window.
#  3. Either missing: the browser, with a one-line note in the panel on how to get the window.
#  4. The window fails to open for any other reason: the browser, with a note saying so.
APP_WINDOW = None            # the main pywebview window while it is open
WINDOW_NOTE = ""             # shown at the top of the panel after a fallback to the browser
BASE_URL = ""
WEBVIEW2_CLIENT = r"Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
WEBVIEW2_URL = "https://developer.microsoft.com/microsoft-edge/webview2/consumer/"


def webview2_installed():
    """Windows only: is the WebView2 Runtime installed? Microsoft's documented check: the
    "pv" value under its EdgeUpdate client key, per machine (64- or 32-bit Windows) or per
    user, holding a version above 0.0.0.0. Other systems: True (they don't use it)."""
    if os.name != "nt":
        return True
    import winreg
    places = [(winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\WOW6432Node\\" + WEBVIEW2_CLIENT),
              (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\" + WEBVIEW2_CLIENT),
              (winreg.HKEY_CURRENT_USER, "Software\\" + WEBVIEW2_CLIENT)]
    for root, path in places:
        try:
            with winreg.OpenKey(root, path) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
            if version and str(version).strip() not in ("", "0.0.0.0"):
                return True
        except OSError:
            pass
    return False


def window_support():
    """(True, "") if the app window can be tried, else (False, note for the panel)."""
    try:
        import webview  # noqa: F401  (pywebview)
    except Exception:
        if getattr(sys, "frozen", False):
            return False, ("The app window isn't available in this build, so the panel opened "
                           "in your browser.")
        pip = "py -m pip install pywebview" if os.name == "nt" else "python3 -m pip install pywebview"
        return False, ("To use Melodarium in its own window instead of the browser, "
                       f"install pywebview ({pip}) and reopen the app.")
    if not webview2_installed():
        return False, ("To use Melodarium in its own window instead of the browser, install "
                       "Microsoft's free WebView2 Runtime and reopen the app: " + WEBVIEW2_URL)
    return True, ""


class WindowApi:
    """Called from the panel (window.pywebview.api...) when it runs in the app window."""

    def __init__(self):
        self._preview = None

    def open_window(self, path, title, kind=""):
        """Open one of the app's pages (the preview PDF, the acknowledgements) in a
        separate window. Returns False if that failed, so the panel can use the browser."""
        import webview
        try:
            if kind == "preview" and self._preview is not None:
                try:
                    self._preview.destroy()          # one preview window at a time
                except Exception:
                    pass
            w = webview.create_window(title, BASE_URL + path, width=900, height=1100,
                                      min_size=(400, 300))
            if kind == "preview":
                self._preview = w
            return True
        except Exception:
            return False


def bring_window_to_front():
    w = APP_WINDOW
    if w is None:
        return False
    try:
        w.restore()
        w.show()
        w.on_top = True                      # brief "always on top" lifts it above the others
        threading.Timer(0.4, lambda: setattr(w, "on_top", False)).start()
    except Exception:
        pass
    return True


def run_app_window(url):
    """Show the panel in its own window and block until it is closed.
    Raises RuntimeError if the window never appeared."""
    global APP_WINDOW
    import webview
    shown = threading.Event()
    window = webview.create_window(APP_NAME, url, width=1280, height=900, min_size=(760, 560),
                                   background_color="#f6f5f2", js_api=WindowApi())
    window.events.shown += lambda *a: shown.set()
    APP_WINDOW = window
    try:
        try:
            webview.start(gui="edgechromium" if os.name == "nt" else None)
        except (ValueError, KeyError, TypeError):
            webview.start()                  # this pywebview names its back ends differently
    finally:
        APP_WINDOW = None
    if not shown.is_set():
        raise RuntimeError("the window didn't appear")


def say_console(text):
    """print(), but quiet when there is no console (the packaged Windows app has none)."""
    try:
        if sys.stdout:
            print(text, flush=True)
    except Exception:
        pass


def already_running():
    """URL of a copy of this app that is already running, or None."""
    import urllib.request
    url = f"http://127.0.0.1:{PORT}"
    try:
        with urllib.request.urlopen(url + "/ping", timeout=1.5) as r:
            if json.loads(r.read().decode()).get("app") == APP_NAME:
                return url
    except Exception:
        pass
    return None


def main():
    global engine, SERVER, BASE_URL, WINDOW_NOTE
    if len(sys.argv) >= 3 and sys.argv[1] == "--pick-folder":
        pick_folder(sys.argv[2])
        return
    running = already_running()
    if running:      # opened again: bring the open window forward, or show the panel in the browser
        try:
            import urllib.request
            with urllib.request.urlopen(running + "/focus", timeout=2) as r:
                if json.loads(r.read().decode()).get("window"):
                    return
        except Exception:
            pass
        webbrowser.open(running)
        return
    engine = Engine()
    threading.Thread(target=installed_fonts, daemon=True).start()   # warm the font list
    threading.Thread(target=find_lilypond, daemon=True).start()     # look for LilyPond
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)  # port busy: pick any free one
    SERVER = server
    url = BASE_URL = f"http://127.0.0.1:{server.server_address[1]}"
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    say_console(f"Control panel: {url}")
    # --browser: always use the web browser; --no-browser: open nothing (for testing)
    use_window = "--browser" not in sys.argv and "--no-browser" not in sys.argv
    try:
        opened = False
        if use_window:
            ok, WINDOW_NOTE = window_support()
            if ok:
                try:
                    say_console("Opening the app window. Closing it quits the app (progress is saved).")
                    run_app_window(url)          # blocks until the window is closed
                    opened = True
                except Exception as e:
                    WINDOW_NOTE = (f"The app window couldn't open ({str(e)[:120] or type(e).__name__}), "
                                   "so the panel opened in your browser.")
        if not opened:
            if WINDOW_NOTE:
                say_console(WINDOW_NOTE)
            say_console("Leave this window open while it runs. Quit from the panel (or Ctrl+C here).")
            if "--no-browser" not in sys.argv:
                threading.Timer(0.5, lambda: webbrowser.open(url)).start()
            while serving.is_alive():            # until Quit in the panel stops the server
                serving.join(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        engraver.stop()
        engine.stop()
        try:
            server.shutdown()
        except Exception:
            pass
        server.server_close()
        say_console("\nSaved. Goodbye.")


if __name__ == "__main__":
    main()
