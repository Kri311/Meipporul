#!/usr/bin/env python3
"""
Generate the proposed-system architecture diagram for the quantum project:
Hardware-Aware Variational Quantum Framework for the GCI Credit Risk Model.

Same visual language as the FraudLens build_diagram.py (beige page, monospaced
body text, status pills, computed box heights), with one change in meaning:
the pill shows PROVENANCE instead of completion status.

    BASE PAPER       - step taken from the base paper (Eq. numbers kept)
    * OUR ADDITION   - step this project adds
    * OPTIONAL       - our addition, measured but skipped by the deployed pipeline

Produces two files in the current directory:
    quantum_architecture.svg   vector, scales to any size, editable
    quantum_architecture.png   2600 px wide, flattened RGB (no alpha)

Requirements:
    pip install cairosvg pillow

Usage:
    python3 build_quantum_diagram.py

All heights are computed from content, so adding a line to any panel(...) call
below cannot push text outside its border.
"""

W = 1640
PAD = 40
LANE = 60                     # right-hand lane reserved for the re-calibrate loop
BOX_L = PAD
BOX_R = W - PAD - LANE
BOX_W = BOX_R - BOX_L
CX = (BOX_L + BOX_R) / 2
LOOP_X = BOX_R + LANE / 2 + 4
GAP = 40
HALF = (BOX_W - GAP) / 2
LX = BOX_L + HALF / 2
RX = BOX_L + HALF + GAP + HALF / 2

INK = "#1a1208"
RULE = "#1a1208"
MUTED = "#6b5a48"
BODY = "#42342a"
NEUTRAL_BG = "#faf7f0"
CALLOUT_BG = "#efe6d4"
PAGE_BG = "#fdfbf6"
PAGE_RGB = (253, 251, 246)
BAND_BG = "#2e2418"

TAGS = {
    # key : (pill bg, border / accent, pill text, label)
    "PAPER": ("#ece6da", "#6b5a48", "#4a3c2e", "BASE PAPER"),
    "ADD":   ("#e8f3e6", "#3f7d3a", "#2c5c28", "OUR ADDITION"),
    "OPT":   ("#fdf2dc", "#b8891f", "#8a6612", "OPTIONAL"),
}

out = []
y = PAD


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def rect(x, ty, w, h, fill, stroke, sw=2.5, rx=6, dash=None):
    d = ' stroke-dasharray="%s"' % dash if dash else ""
    out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="%d" '
               'fill="%s" stroke="%s" stroke-width="%s"%s/>'
               % (x, ty, w, h, rx, fill, stroke, sw, d))


def line(x1, y1, x2, y2, head=False, dash=None, sw=3, color=RULE):
    d = ' stroke-dasharray="%s"' % dash if dash else ""
    m = ' marker-end="url(#ar)"' if head else ""
    out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" '
               'stroke-width="%s"%s%s/>' % (x1, y1, x2, y2, color, sw, d, m))


def text(x, ty, s, size=15, weight="normal", anchor="start",
         fill=INK, family="Helvetica, Arial, sans-serif", rotate=None):
    r = ' transform="rotate(%d %.1f %.1f)"' % (rotate, x, ty) if rotate else ""
    out.append('<text x="%.1f" y="%.1f" font-family="%s" font-size="%s" '
               'font-weight="%s" text-anchor="%s" fill="%s"%s>%s</text>'
               % (x, ty, family, size, weight, anchor, fill, r, esc(s)))


def mono(x, ty, s, size=13.5, fill=BODY, weight="normal", anchor="start",
         rotate=None):
    # SVG collapses runs of whitespace; non-breaking spaces keep alignment.
    s = s.replace("  ", "\u00a0\u00a0")
    text(x, ty, s, size=size, weight=weight, anchor=anchor, fill=fill,
         family="'DejaVu Sans Mono', Consolas, monospace", rotate=rotate)


def pill(x, ty, key, w=148):
    bg, bd, tx, label = TAGS[key]
    rect(x, ty, w, 24, bg, bd, sw=1.6, rx=12)
    text(x + w / 2, ty + 16.5, label, size=12.5, weight="bold",
         anchor="middle", fill=tx)


def style_for(ln):
    """Highlight USE / RESULT rows the way FraudLens highlighted ELAPSED."""
    s = ln.lstrip()
    if s.startswith("\u2605 RESULT") or s.startswith("RESULT"):
        return "#2c5c28", "bold"
    if s.startswith("\u2605 USE") or s.startswith("USE"):
        return INK, "bold"
    return BODY, "normal"


def panel(x, ty, w, tag_text, title, lines, key, subtitle=None,
          size=13.5, lh=20, title_size=17, dash=None):
    """Draw one stage box at (x, ty). Returns its height."""
    head = 42
    sub = 22 if subtitle else 0
    h = head + sub + len(lines) * lh + 20
    _, bd, _, _ = TAGS[key]
    rect(x, ty, w, h, NEUTRAL_BG, bd, dash=dash)
    out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="4" rx="2" '
               'fill="%s"/>' % (x, ty, w, bd))
    label = ("%s  -  %s" % (tag_text, title)) if tag_text else title
    text(x + 18, ty + 30, label, size=title_size, weight="bold")
    pill(x + w - 148 - 16, ty + 12, key)
    yy = ty + head + 14
    if subtitle:
        mono(x + 18, yy, subtitle, size=12.5, fill="#7a6753", weight="bold")
        yy += sub
    for ln in lines:
        fill, weight = style_for(ln)
        mono(x + 18, yy, ln, size=size, fill=fill, weight=weight)
        yy += lh
    return h


def stage(tag_text, title, lines, key, subtitle=None, x=BOX_L, w=BOX_W,
          dash=None):
    global y
    y += panel(x, y, w, tag_text, title, lines, key, subtitle, dash=dash)


def arrow(cx=CX, length=38, label=None):
    global y
    line(cx, y, cx, y + length, head=True)
    if label:
        mono(cx + 14, y + length / 2 + 4, label, size=12, fill=MUTED)
    y += length


def band(title, sub):
    """Dark section divider - one per PART in the text architecture."""
    global y
    h = 46
    rect(BOX_L, y, BOX_W, h, BAND_BG, BAND_BG, sw=0, rx=4)
    text(BOX_L + 18, y + 30, title, size=17, weight="bold", fill="#fdfbf6")
    mono(BOX_R - 18, y + 29, sub, size=12.5, fill="#d9ccb4", anchor="end")
    y += h


def callout(title, lines, cw=820):
    global y
    ch = 58 + 20 * len(lines)
    rect(CX - cw / 2, y, cw, ch, CALLOUT_BG, INK, sw=3)
    text(CX, y + 38, title, size=22, weight="bold", anchor="middle")
    ty = y + 64
    for ln in lines:
        mono(CX, ty, ln, size=13, anchor="middle", fill="#4a3c2e")
        ty += 20
    y += ch


# ================================================================ title
TITLE_H = 160
rect(BOX_L, y, BOX_W, TITLE_H, "#ffffff", INK, sw=3.5)
text(CX, y + 42, "PROPOSED SYSTEM ARCHITECTURE", size=27, weight="bold",
     anchor="middle")
mono(CX, y + 68, "Hardware-Aware Variational Quantum Framework for the "
     "GCI Credit Risk Model", size=14.5, anchor="middle", fill="#4a3c2e")
mono(CX, y + 90, "Replication of the base paper  +  noisy-device "
     "calibration, mitigation and closed-loop repair",
     size=13, anchor="middle", fill="#7a6753")
mono(CX, y + 112, "Qiskit AerSimulator with injected noise  -  "
     "laptop-grade, no physical QPU", size=12.5, anchor="middle",
     fill="#2c5c28")
# legend
lx0 = CX - (3 * 148 + 2 * 24) / 2
for i, k in enumerate(("PAPER", "ADD", "OPT")):
    pill(lx0 + i * (148 + 24), y + 124, k)
y += TITLE_H
arrow()

# ================================================================ PART A
band("PART A  -  REPLICATION", "base paper, equation numbers as published")
y += 20

# two independent columns
top = y
FIN_X, FIN_W = BOX_L, HALF
LOAD_X, LOAD_W = BOX_L + HALF + GAP, HALF - 52   # room for the p* bypass
FIN_CX = FIN_X + FIN_W / 2
LOAD_CX = LOAD_X + LOAD_W / 2

text(FIN_CX, y + 14, "FINANCE BRANCH", size=15, weight="bold", anchor="middle")
mono(FIN_CX, y + 34, "builds the asset gates", size=12.5, anchor="middle",
     fill=MUTED)
text(LOAD_X + HALF / 2, y + 14, "LOADER BRANCH", size=15, weight="bold",
     anchor="middle")
mono(LOAD_X + HALF / 2, y + 34, "builds the trained angles", size=12.5,
     anchor="middle", fill=MUTED)
top += 50

MINI = dict(size=12.5, lh=18, title_size=15)
STEP = 44


def column(x, w, cx, steps, y0):
    """Stack mini panels with 'passes:' arrows. Returns (bottom_y, boxes)."""
    yy = y0
    boxes = []
    for i, (tag, title, lines, passes) in enumerate(steps):
        h = panel(x, yy, w, tag, title, lines, "PAPER", **MINI)
        boxes.append((yy, h))
        yy += h
        if i < len(steps) - 1:
            line(cx, yy, cx, yy + STEP, head=True)
            mono(cx + 12, yy + STEP / 2 + 4, "passes: " + passes, size=11.5,
                 fill=MUTED)
            yy += STEP
    return yy, boxes


fin_bottom, _ = column(FIN_X, FIN_W, FIN_CX, [
    ("Eq. 1", "Vasicek PD(z)", [
        "PD(z) = \u03a6( (\u03a6\u207b\u00b9(p0) - \u221a\u03c1\u00b7z) / \u221a(1-\u03c1) )",
        "needs  p0 = 0.25,  \u03c1 = 0.027",
    ], "PD(z) curve"),
    ("Eq. 2", "Linearise onto the Born rule", [
        "PD(z) = sin\u00b2(\u03b1z + \u03b2)",
        "fit \u03b1, \u03b2 so the asset qubit reproduces PD(z)",
    ], "\u03b1, \u03b2"),
    ("Eq. 3", "Rotation angle", [
        "Ry( 2(\u03b1z + \u03b2) )",
        "P(|1>) on the asset qubit = default probability",
    ], "rotation angle 2(\u03b1z + \u03b2)"),
    ("Eq. 4", "Register-indexed asset gates", [
        "Ry( 2(\u03b1~\u00b7b + \u03b2~) )",
        "controlled on the z-register index b",
    ], ""),
], top)

load_bottom, load_boxes = column(LOAD_X, LOAD_W, LOAD_CX, [
    ("Eq. 10", "Target Gaussian p*_b", [
        "needs z-grid  z(b) in [-3, 3]",
    ], "target histogram p*  (held until Eq. 11)"),
    ("Eq. 5", "Register size", [
        "N_qubits = N_assets + \u03a3 n_k",
    ], "register size (n + 1 qubits)"),
    ("Eq. 6", "Goal state", [
        "|\u03c8(\u03b8)> = \u03a3 \u221ap_b |b>",
    ], "goal state to build"),
    ("Eq. 12, 13", "Ry matrix + CNOT", [
        "z-register ansatz: Ry(\u03b8) rotations + CNOT entangler",
    ], "amplitudes as functions of \u03b8"),
    ("Eq. 8, 9", "Circuit histogram", [
        "p_b(\u03b8) = |<b|\u03c8(\u03b8)>|\u00b2",
    ], "circuit histogram p(\u03b8)"),
    ("Eq. 11", "MSE loss", [
        "L(\u03b8) = \u03a3 (p_b(\u03b8) - p*_b)\u00b2      \u25c4 p*",
    ], "loss to differentiate"),
    ("Paper, unnumbered", "Parameter-shift gradient", [
        "exact analytical \u2202L/\u2202\u03b8 from shifted circuits",
    ], "gradients \u2202L/\u2202\u03b8"),
    ("Paper, unnumbered", "Adam update", [
        "\u03b8 \u2190 Adam(\u03b8, \u2202L/\u2202\u03b8)  until convergence",
    ], ""),
], top)

# p* bypass: Eq. 10 -> Eq. 11 along the right edge of the loader column
(e10_y, e10_h), (e11_y, e11_h) = load_boxes[0], load_boxes[5]
BYX = LOAD_X + LOAD_W + 26
line(LOAD_X + LOAD_W, e10_y + e10_h / 2, BYX, e10_y + e10_h / 2, dash="7 5",
     sw=2.2)
line(BYX, e10_y + e10_h / 2, BYX, e11_y + e11_h / 2, dash="7 5", sw=2.2)
line(BYX, e11_y + e11_h / 2, LOAD_X + LOAD_W + 2, e11_y + e11_h / 2,
     head=True, dash="7 5", sw=2.2)
mono(BYX + 16, (e10_y + e11_y) / 2 + 120, "p* held for Eq. 11", size=11.5,
     fill=MUTED, rotate=90)

# merge both columns into the full circuit
merge = max(fin_bottom, load_bottom) + 34
line(FIN_CX, fin_bottom, FIN_CX, merge)
mono(FIN_CX + 12, fin_bottom + 26, "passes: asset-qubit gates (\u03b1~, \u03b2~)",
     size=11.5, fill=MUTED)
line(LOAD_CX, load_bottom, LOAD_CX, merge)
mono(LOAD_CX + 12, load_bottom + 22, "passes: trained angles \u03b8*",
     size=11.5, fill=MUTED)
line(FIN_CX, merge, LOAD_CX, merge)
y = merge
arrow()

callout("FULL GCI CIRCUIT", ["loader \u03b8*  +  asset gates  "
                             "(\u03b1~, \u03b2~)  on n + 1 qubits"], cw=640)
arrow(label="passes: logical circuit")

stage("Paper, unnumbered", "SABRE TRANSPILATION", [
    "SABRE layout + routing onto a mock coupling map (limited connectivity)",
    "native gate set:  rz, sx, x, cz",
    "minimises SWAP insertion and depth; before / after gate-count comparison",
], "PAPER")
arrow(label="passes: hardware circuit")

# ================================================================ PART B
band("PART B  -  NOISY DEVICE", "our addition")
y += 20

stage("ADDITION 1", "NOISE-EMULATED DEVICE", [
    "depolarizing 0.2 % (1q) / 1.5 % (2q)   |   readout 2-7 % per qubit",
    "drift   \u03b8_real = (1 + \u03b5)\u00b7\u03b8 + \u03b4      (hidden from every method)",
    "",
    "\u2605 USE:    runs the paper's hardware experiment on a laptop with the same",
    "          three error sources the paper names (Sec. V)",
    "\u2605 RESULT: trained angles fall from fidelity 1.00 to 0.88 / 0.92",
], "ADD", subtitle="Qiskit AerSimulator + injected noise model")
arrow(label="passes: measured distribution p_dev(x)")

stage("ADDITION 2", "CALIBRATION OBJECTIVE", [
    "J(x) = H( p_device(x), p_reference )      Hellinger distance",
    "",
    "\u2605 USE:    one number an algorithm can minimise; measured on readout-",
    "          corrected data so mitigation doesn't double-correct",
], "ADD")
arrow(label="passes: the number to minimise")

# ================================================================ PART C
band("PART C  -  CALIBRATION", "two alternatives, compared")
y += 20

# side branch (feeds 6A only) sits in the left half; main flow passes centre
sb_top = y
sb_h = panel(BOX_L, y, HALF, "Eq. 14-17", "Symmetry conditions", [
    "SIDE BRANCH - feeds 6A only",
    "derived from Eq. 12-13  ->  search ranges for 6A",
    "6B does not use them",
], "PAPER", dash="8 5", **MINI)
mono(RX, y + sb_h / 2 + 4, "J(x) feeds BOTH methods", size=12.5,
     anchor="middle", fill=MUTED)
line(CX, y - 20, CX, y + sb_h + 22)
y += sb_h + 22
line(LX, sb_top + sb_h, LX, y)          # side branch drops into the 6A arrow
line(LX, y, RX, y)
line(LX, y, LX, y + 42, head=True)
line(RX, y, RX, y + 42, head=True)
mono(LX + 12, y + 26, "ranges", size=11.5, fill=MUTED)
y += 42

top = y
h6a = panel(BOX_L, top, HALF, "6A  -  paper", "GRID SWEEP", [
    "\u03b81: 21\u00b0 -> 1\u00b0 steps",
    "\u03b82: 36\u00b0 -> 7.5\u00b0 / 14.5\u00b0",
    "asset angles on a 2-D grid",
    "\u03b80 never tuned",
    "manual, brute-force, per qubit pair",
    "",
    "",
    "RESULT: F = 0.939 / 0.957",
    "        347 / 477 runs",
], "PAPER")
h6b = panel(BOX_L + HALF + GAP, top, HALF, "6B  -  ADDITION 3", "AUTOMATED CALIBRATION", [
    "1. Bayesian optimisation - loader angles",
    "2. Bayesian optimisation - asset angles",
    "3. SPSA - all angles together",
    "4. verify, keep the better candidate",
    "",
    "\u2605 USE:    replaces manual brute force",
    "",
    "\u2605 RESULT: F = 0.982 / 0.994",
    "          204 runs",
], "ADD")
H6 = max(h6a, h6b)
LOOP_TARGET_Y = top + H6 / 2
y = top + H6

line(LX, y, LX, y + 26)
line(RX, y, RX, y + 26)
line(LX, y + 26, RX, y + 26)
y += 26
arrow(label="passes: calibrated angles x*")

callout("CALIBRATED ANGLES x*", [
    "grid sweep  F = 0.939 / 0.957 in 347 / 477 runs   ->   "
    "automated  F = 0.982 / 0.994 in 204 runs",
    "(2-qubit / 3-qubit)   higher fidelity with fewer device runs",
], cw=1000)
arrow()

# ================================================================ PART D
band("PART D  -  EXECUTION + MITIGATION", "our addition")
y += 20

stage("ADDITION 4", "REPEATED EXECUTION", [
    "20 runs \u00d7 20 000 shots",
    "\u2605 USE:    error bars -> results are statistically proven",
], "ADD")
arrow(label="passes: raw measured histograms")

stage("ADDITION 5", "READOUT MITIGATION", [
    "m = A\u00b7p  ->  solve for p  (NNLS)",
    "\u2605 USE:    undoes measurement bit-flips (the paper applied none)",
    "\u2605 RESULT: alone it can't fix drift (0.92 / 0.91); essential after retuning",
], "ADD")

# ZNE is optional: inset box with a dashed bypass on the left
BYPASS_X = BOX_L + 40
rem_bottom = y
line(CX, y, CX, y + 40, head=True)
mono(CX + 12, y + 24, "passes: readout-corrected distribution", size=12,
     fill=MUTED)
y += 40
zne_h = panel(BOX_L + 110, y, BOX_W - 110, "ADDITION 6", "ZERO-NOISE EXTRAPOLATION", [
    "noise \u00d71, \u00d73, \u00d75  ->  extrapolate to \u00d70",
    "\u2605 USE:    removes part of the remaining gate noise (paper only discussed it)",
    "\u2605 RESULT: 0.982 -> 0.998 (2q), 0.995 -> 0.996 (3q); costs up to 9\u00d7 gate time",
], "OPT", subtitle="optional variant", dash="9 5")
y += zne_h
end = y + 40
line(BYPASS_X, rem_bottom + 14, BYPASS_X, end - 6, dash="7 5", sw=2.2)
line(CX, rem_bottom + 14, BYPASS_X, rem_bottom + 14, dash="7 5", sw=2.2)
mono(BYPASS_X + 16, rem_bottom + 44, "deployed: REM -> post-proc",
     size=11.5, fill=MUTED, rotate=90)
line(CX, y, CX, end)
line(BYPASS_X, end - 6, CX, end - 6, dash="7 5", sw=2.2)
y = end
arrow(length=26)

callout("CORRECTED DISTRIBUTION  p(default, z)", [
    "readout-mitigated  (+ ZNE in the optional variant)",
], cw=760)
arrow()

# ================================================================ PART E
band("PART E  -  RISK NUMBERS", "paper method + our checks")
y += 20

stage("Sec. IV-C", "POST-PROCESSING", [
    "right bits -> z index -> P(Z = z_b)   \u00b7   left bit -> default -> "
    "loss = d \u00d7 $1000",
    "losses -> PDF -> CDF   \u00b7   expected loss = \u03a3 L\u00b7P(L)",
], "PAPER")
arrow(label="passes: loss PDF/CDF + joint p(default, z)")

stage("ADDITION 7", "CONDITIONAL-DEFAULT CHECK", [
    "P(default | z_b) = p(1, b) / P(z_b)   +   four fidelity metrics",
    "\u25c4 compared against Eq. 1 again (classical reference)",
    "",
    "\u2605 USE:    checks the financial model itself survives the noise;",
    "          separates hardware error from modelling error",
], "ADD")
arrow(label="passes: CDF + distributions")

stage("Paper", "VaR & HELLINGER FIDELITY", [
    "VaR_0.95 = min{ L : CDF(L) \u2265 0.95 }   ->  $1000   (matches the paper)",
    "F_H = ( \u03a3 \u221a(p\u00b7q) )\u00b2          vs. the classical Vasicek / GCI baseline",
], "PAPER")
arrow(label="passes: fidelity F_H")

# ================================================================ PART F
band("PART F  -  CLOSED LOOP", "our addition")
y += 24

# decision diamond
DW, DH = 380, 130
dtop = y
pts = "%.1f,%.1f %.1f,%.1f %.1f,%.1f %.1f,%.1f" % (
    CX, dtop, CX + DW / 2, dtop + DH / 2, CX, dtop + DH, CX - DW / 2, dtop + DH / 2)
out.append('<polygon points="%s" fill="%s" stroke="%s" stroke-width="2.5"/>'
           % (pts, NEUTRAL_BG, TAGS["ADD"][1]))
text(CX, dtop + 52, "F_H \u2265 0.97 ?", size=20, weight="bold",
     anchor="middle", family="'DejaVu Sans', sans-serif")
mono(CX, dtop + 78, "ADDITION 8 - fidelity gate", size=12.5, anchor="middle", fill=MUTED)
mid = dtop + DH / 2
line(CX - DW / 2, mid, LX, mid)
line(LX, mid, LX, dtop + DH + 30, head=True)
line(CX + DW / 2, mid, RX, mid)
line(RX, mid, RX, dtop + DH + 30, head=True)
text((CX - DW / 2 + LX) / 2, mid - 10, "YES", size=14, weight="bold",
     anchor="middle", fill="#2c5c28")
text((CX + DW / 2 + RX) / 2, mid - 10, "NO", size=14, weight="bold",
     anchor="middle", fill="#8a2f2f")
y = dtop + DH + 30

top = y
ha = panel(BOX_L, top, HALF, "", "ACCEPT", [
    "fidelity above threshold",
    "distribution validated -> report VaR",
    "",
    "",
    "",
    "",
    "",
], "ADD")
hb = panel(BOX_L + HALF + GAP, top, HALF, "", "RE-CALIBRATE", [
    "fidelity below threshold -> re-run 6B,",
    "starting from the current angles",
    "",
    "\u2605 USE:    chips drift; the system detects",
    "          it and repairs itself",
    "\u2605 RESULT: drift event 0.53 -> 0.97 (2q),",
    "          0.68 -> 0.99 (3q), 204 runs each",
], "ADD")
HF = max(ha, hb)
loop_src = top + hb / 2
y = top + HF

# loop back: RE-CALIBRATE -> lane -> 6B
line(BOX_R, loop_src, LOOP_X, loop_src)
line(LOOP_X, loop_src, LOOP_X, LOOP_TARGET_Y)
line(LOOP_X, LOOP_TARGET_Y, BOX_R + 2, LOOP_TARGET_Y, head=True)
mono(LOOP_X + 16, (loop_src + LOOP_TARGET_Y) / 2,
     "passes: current angles as starting point  ->  back to 6B",
     size=12, fill=MUTED, anchor="middle", rotate=-90)
y += 30

# ============================================================ footer
FH = 128
rect(BOX_L, y, BOX_W, FH, "#f2ece0", INK, sw=3)
text(CX, y + 34, "EXECUTION ENVIRONMENT", size=18, weight="bold",
     anchor="middle")
mono(CX, y + 62, "Every stage above runs on a laptop-grade Qiskit "
     "AerSimulator - no physical QPU dependency.", size=13.5,
     anchor="middle")
mono(CX, y + 82, "The noise model carries the three error sources the paper "
     "names (Sec. V): gate depolarisation,", size=13.5, anchor="middle")
mono(CX, y + 102, "readout bit-flips and calibration drift. The drift "
     "(\u03b5, \u03b4) is hidden from every calibration method.",
     size=13.5, anchor="middle")
y += FH + PAD

# ============================================================ write out
H = int(y)
svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
       'viewBox="0 0 %d %d">' % (W, H, W, H),
       '<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" '
       'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
       '<path d="M 0 0 L 10 5 L 0 10 z" fill="%s"/></marker></defs>' % RULE,
       '<rect x="0" y="0" width="{}" height="{}" fill="{}"/>'.format(W, H, PAGE_BG)]
svg += out
svg.append("</svg>")

SVG_PATH = "quantum_architecture.svg"
PNG_PATH = "quantum_architecture.png"
PNG_WIDTH = 2600

with open(SVG_PATH, "w", encoding="utf-8") as fh:
    fh.write("\n".join(svg))
print("SVG written: %s  (%d x %d)" % (SVG_PATH, W, H))

# Rasterise to an OPAQUE PNG (flatten any alpha onto the page colour).
try:
    import cairosvg
    from PIL import Image

    cairosvg.svg2png(url=SVG_PATH, write_to=PNG_PATH,
                     output_width=PNG_WIDTH, background_color=PAGE_BG)
    im = Image.open(PNG_PATH)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        canvas = Image.new("RGB", im.size, PAGE_RGB)
        canvas.paste(im, mask=im.split()[-1])
        im = canvas
    else:
        im = im.convert("RGB")
    im.save(PNG_PATH, "PNG", optimize=True)
    check = Image.open(PNG_PATH)
    assert "A" not in check.mode, "PNG still has an alpha channel"
    print("PNG written: %s  (%d x %d, mode %s)"
          % (PNG_PATH, check.size[0], check.size[1], check.mode))
except ImportError:
    print("PNG skipped -- install the renderers first:")
    print("    pip install cairosvg pillow")
