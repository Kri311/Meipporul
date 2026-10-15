#!/usr/bin/env python3
"""Build a Veritas Lens end-to-end workflow diagram.

The visual language follows build_quantum_diagram.py and
flow_chart_template.jpeg (warm paper background, dark section bands,
provenance/status pills, thin connectors). This is a separate artifact so the
quantum-project diagram and its source remain untouched.

Run from the repository root or any directory:
    python flow_chart/build_veritas_lens_diagram.py

Writes flow_chart/veritas_lens_workflow.png and .svg.
"""

from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
PNG_PATH = ROOT / "veritas_lens_workflow.png"
SVG_PATH = ROOT / "veritas_lens_workflow.svg"

WIDTH = 1700
PAGE = (253, 251, 246)
PANEL = (250, 247, 240)
CALLOUT = (239, 230, 212)
INK = (26, 18, 8)
BODY = (66, 52, 42)
MUTED = (107, 90, 72)
BAND = (46, 36, 24)
GREEN = (63, 125, 58)
GREEN_BG = (232, 243, 230)
GOLD = (184, 137, 31)
GOLD_BG = (253, 242, 220)
GREY_BG = (236, 230, 218)
GREY = (107, 90, 72)

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")


def font(name, size):
    path = FONT_DIR / name
    return ImageFont.truetype(str(path), size) if path.exists() else ImageFont.load_default()


F_TITLE = font("DejaVuSans-Bold.ttf", 34)
F_SUBTITLE = font("DejaVuSans.ttf", 19)
F_BAND = font("DejaVuSans-Bold.ttf", 20)
F_BODY = font("DejaVuSansMono.ttf", 17)
F_HEADING = font("DejaVuSans-Bold.ttf", 21)
F_PILL = font("DejaVuSans-Bold.ttf", 14)


class Diagram:
    def __init__(self):
        # The complete workflow is taller than the initial 3000px draft.
        # PIL does not extend an image when cropping past its bottom; it pads
        # that area with black, so allocate a safe canvas before cropping.
        self.image = Image.new("RGB", (WIDTH, 5000), PAGE)
        self.draw = ImageDraw.Draw(self.image)
        self.svg = []
        self.y = 36
        self.main_x = 52
        self.main_w = WIDTH - 104
        self.center = self.main_x + self.main_w // 2
        self.records = {}

    def _svg_rect(self, x, y, w, h, fill, stroke=INK, sw=2, rx=8, dash=None):
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        self.svg.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{dash_attr}/>'
        )

    @staticmethod
    def _hex(rgb):
        return "#%02x%02x%02x" % rgb

    def text(self, x, y, value, fnt, fill=INK, anchor="la"):
        self.draw.text((x, y), value, font=fnt, fill=fill, anchor=anchor)
        self.svg.append(
            f'<text x="{x}" y="{y}" font-family="DejaVu Sans" '
            f'font-size="{fnt.size}" fill="{self._hex(fill)}" '
            f'text-anchor="{"middle" if anchor.startswith("m") else "start"}" '
            f'dominant-baseline="middle">{escape(value)}</text>'
        )

    def line(self, x1, y1, x2, y2, color=INK, width=3, dash=None, arrow=False):
        self.draw.line((x1, y1, x2, y2), fill=color, width=width)
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        self.svg.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{self._hex(color)}" stroke-width="{width}"{dash_attr}/>'
        )
        if dash:
            # Repaint a dashed connector in PIL for parity with the SVG.
            self.draw.line((x1, y1, x2, y2), fill=PAGE, width=width + 1)
            length = abs(x2 - x1) + abs(y2 - y1)
            if length:
                n = max(1, int(length // 14))
                for i in range(n):
                    if i % 2 == 0:
                        a, b = i / n, min(1, (i + 1) / n)
                        self.draw.line((x1 + (x2 - x1) * a, y1 + (y2 - y1) * a,
                                        x1 + (x2 - x1) * b, y1 + (y2 - y1) * b),
                                       fill=color, width=width)
        if arrow:
            if y2 >= y1 and x1 == x2:
                pts = [(x2, y2), (x2 - 9, y2 - 14), (x2 + 9, y2 - 14)]
            elif x2 >= x1:
                pts = [(x2, y2), (x2 - 14, y2 - 9), (x2 - 14, y2 + 9)]
            else:
                pts = [(x2, y2), (x2 + 14, y2 - 9), (x2 + 14, y2 + 9)]
            self.draw.polygon(pts, fill=color)
            self.svg.append(
                f'<polygon points="{pts[0][0]},{pts[0][1]} {pts[1][0]},{pts[1][1]} '
                f'{pts[2][0]},{pts[2][1]}" fill="{self._hex(color)}"/>'
            )

    def pill(self, x, y, key, label):
        styles = {
            "BASE": (GREY_BG, GREY, (74, 60, 46)),
            "MODEL": (GREEN_BG, GREEN, (44, 92, 40)),
            "OPTIONAL": (GOLD_BG, GOLD, (138, 102, 18)),
        }
        bg, border, fg = styles[key]
        bbox = self.draw.textbbox((0, 0), label, font=F_PILL)
        w = max(126, bbox[2] + 24)
        h = 28
        self.draw.rounded_rectangle((x, y, x + w, y + h), radius=14,
                                    fill=bg, outline=border, width=2)
        self.draw.text((x + w / 2, y + h / 2), label, font=F_PILL,
                       fill=fg, anchor="mm")
        self.svg.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" '
            f'fill="{self._hex(bg)}" stroke="{self._hex(border)}" stroke-width="2"/>'
        )
        self.svg.append(
            f'<text x="{x + w / 2}" y="{y + h / 2}" font-family="DejaVu Sans" '
            f'font-weight="bold" font-size="{F_PILL.size}" fill="{self._hex(fg)}" '
            f'text-anchor="middle" dominant-baseline="middle">{escape(label)}</text>'
        )

    def title(self):
        x, y, w, h = 52, self.y, WIDTH - 104, 150
        self.draw.rounded_rectangle((x, y, x + w, y + h), radius=10,
                                    fill=(255, 255, 255), outline=INK, width=3)
        self._svg_rect(x, y, w, h, "#ffffff", sw=3, rx=10)
        self.text(WIDTH // 2, y + 38, "VERITAS LENS — NEWS INTELLIGENCE PIPELINE",
                  F_TITLE, anchor="mm")
        self.text(WIDTH // 2, y + 78,
                  "RSS ingestion  ·  bilingual NER  ·  E5 event clustering  ·  summaries  ·  web delivery",
                  F_SUBTITLE, fill=BODY, anchor="mm")
        self.text(WIDTH // 2, y + 112,
                  "English + Tamil  |  PostgreSQL source of truth  |  trafiltura_preprocessed.csv canonical export",
                  F_SUBTITLE, fill=MUTED, anchor="mm")
        self.y += h + 28

    def band(self, title, note):
        x, y, w, h = 52, self.y, WIDTH - 104, 48
        self.draw.rounded_rectangle((x, y, x + w, y + h), radius=5, fill=BAND)
        self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" fill="{self._hex(BAND)}"/>')
        self.text(x + 20, y + h / 2, title, F_BAND, fill=(253, 251, 246), anchor="lm")
        note_bbox = self.draw.textbbox((0, 0), note, font=F_SUBTITLE)
        self.text(x + w - note_bbox[2] - 20, y + h / 2, note,
                  F_SUBTITLE, fill=(217, 204, 180), anchor="lm")
        self.y += h + 18

    def panel(self, title, lines, key="BASE", label="", subtitle=None,
              x=None, w=None, dash=None, track=None):
        x = self.main_x if x is None else x
        w = self.main_w if w is None else w
        row_h = 27
        title_h = 48
        subtitle_h = 26 if subtitle else 0
        h = title_h + subtitle_h + row_h * len(lines) + 18
        styles = {
            "BASE": (GREY, "#faf7f0"),
            "MODEL": (GREEN, "#faf7f0"),
            "OPTIONAL": (GOLD, "#faf7f0"),
        }
        border, bg = styles[key]
        self.draw.rounded_rectangle((x, self.y, x + w, self.y + h), radius=8,
                                    fill=bg, outline=border, width=3)
        self.draw.rounded_rectangle((x, self.y, x + w, self.y + 7), radius=3, fill=border)
        self._svg_rect(x, self.y, w, h, bg, stroke=border, sw=3, dash=dash)
        self.draw.rectangle((x + 5, self.y + 3, x + w - 5, self.y + 8), fill=border)
        self.text(x + 20, self.y + 28, title, F_HEADING)
        if label:
            self.pill(x + w - 160, self.y + 10, key, label)
        body_y = self.y + title_h
        if subtitle:
            self.text(x + 20, body_y + 3, subtitle, F_PILL, fill=MUTED)
            body_y += subtitle_h
        for index, value in enumerate(lines):
            color = GREEN if value.startswith("RESULT:") else BODY
            weight = F_HEADING if value.startswith("RESULT:") else F_BODY
            self.text(x + 20, body_y + 8 + index * row_h, value, weight, fill=color)
        if track:
            self.records[track] = (x, self.y, w, h)
        y_top = self.y
        self.y += h
        return y_top, h

    def arrow(self, label=None):
        start, end = self.y + 2, self.y + 38
        self.line(self.center, start, self.center, end, arrow=True)
        if label:
            self.text(self.center + 18, (start + end) / 2, label, F_PILL, fill=MUTED)
        self.y = end + 8

    def build(self):
        self.title()
        self.band("A  ·  FEED INGESTION AND CLEANING", "RSS sources → verified, normalized article text")
        self.panel("CONFIGURED NEWS FEEDS", [
            "Enabled native RSS / Google News feeds for English and Tamil outlets",
            "Fetch publication time, title, URL, snippet, metadata and lead image",
        ], label="INPUT")
        self.arrow()
        self.panel("FETCH FULL ARTICLE AND APPLY QUALITY GATES", [
            "Trafilatura extracts page text when available; RSS content is the fallback",
            "Reject stale/duplicate items, title–page mismatches and unusable short text",
            "Select article image; reject generic or unrelated feed artwork",
        ], key="MODEL", label="EXTRACTION")
        self.arrow()
        self.panel("CLEAN AND NORMALIZE", [
            "Remove HTML, outlet/editor boilerplate, duplicate text and bad source fragments",
            "Apply outlet-specific cleaners; normalize dates, language, title and body",
            "Keep accepted source content in a consistent title + body representation",
        ], key="MODEL", label="NORMALIZATION")
        self.arrow()
        self.panel("PERSIST CANONICAL ARTICLES", [
            "PostgreSQL stores article rows, metadata, image and processing state",
            "trafiltura_preprocessed.csv is rebuilt from PostgreSQL as the canonical export",
        ], label="DATABASE + CSV", track="store")
        self.arrow()

        self.panel("OPTIONAL OFFLINE NER TRAINING", [
            "Build bilingual corpus from canonical CSV; Babelscape teacher + gazetteer create weak BIO labels",
            "Split by article, fine-tune MuRIL, then evaluate; only enable after independent review",
            "If skipped or unvalidated, production NER uses the Babelscape multilingual baseline",
        ], key="OPTIONAL", label="OPTIONAL", dash="9 6")
        self.arrow(label="validated MuRIL checkpoint or default baseline")

        self.band("B  ·  ENTITY AND SEMANTIC ENRICHMENT", "per-article features → cohesive event groups")
        self.panel("BILINGUAL NAMED ENTITY RECOGNITION", [
            "Default Babelscape multilingual NER; opt-in MuRIL checkpoint after review",
            "Use headline + cleaned body; confidence filter, Tamil normalization and aliases",
            "Store PERSON / ORGANIZATION / LOCATION / DATE and linked entity forms",
        ], key="MODEL", label="NER")
        self.arrow()
        self.panel("MULTILINGUAL E5 EMBEDDINGS", [
            "intfloat/multilingual-e5-base encodes headline and body passages (768 dimensions)",
            "Headline gets higher weight; long bodies are split into chunks",
            "Persist vector, model name and semantic text hash to detect stale embeddings",
        ], key="MODEL", label="EMBEDDINGS")
        self.arrow()
        self.panel("DBSCAN EVENT CLUSTERING", [
            "Cosine-distance DBSCAN; same-language and publication-date guards",
            "NER overlap only corroborates sufficiently similar E5 vectors",
            "Pairwise cohesion splits chaining errors; noise remains a standalone story",
        ], key="MODEL", label="CLUSTERING")
        self.arrow()

        self.band("C  ·  EVENT INTELLIGENCE", "topic, summary and event export are computed before page requests")
        self.panel("TOPIC CLASSIFICATION", [
            "Event title + article text encoded by E5; typed NER features can be fused",
            "Logistic Regression predicts the bilingual taxonomy; rules provide fallback",
            "E5 + NER is selected only when its measured validation gain justifies it",
        ], key="MODEL", label="E5 + NER")
        self.arrow()
        self.panel("PERSIST EVENT BULLET SUMMARIES", [
            "Generate English and Tamil bullets per event before readers open the page",
            "Multilingual XLSum model; source-grounded extractive fallback if unavailable",
            "Save in PostgreSQL by source/model hash; reuse until content changes",
        ], key="MODEL", label="SUMMARIZATION")
        self.arrow()
        self.panel("BUILD ENRICHED EXPORTS", [
            "Generate event representation: headline, dates, location, entities, sources and topic",
            "Export article + summary fields to trafiltura_preprocessed.csv and events_representation.csv",
        ], label="EXPORT")
        self.arrow()

        self.band("D  ·  API, WEB UI AND RECURRING UPDATES", "serving reads stored event data")
        self.panel("FASTAPI EVENT API", [
            "Read PostgreSQL events, article details, sources, image and stored bullet summaries",
            "Reject incohesive legacy clusters from event pages; expose their stories separately",
            "Breaking badge requires recent coverage from at least two independent outlets",
        ], key="MODEL", label="BACKEND")
        self.arrow()
        self.panel("NEXT.JS READER EXPERIENCE", [
            "English / Tamil topic feed, event detail, multi-source articles and bullet summaries",
            "Refresh event feed every 60 seconds; refresh again when a stale tab becomes visible",
        ], key="MODEL", label="FRONTEND")
        self.arrow()
        self.panel("AUTOMATION AND LOCAL SERVICES", [
            "start_daemon.sh runs RSS ingestion + enrichment on a 5-minute cycle by default",
            "start_backend.sh serves FastAPI; start_frontend.sh serves the Next.js development UI",
            "One feed cycle: fetch → normalize/export → NER → E5/DBSCAN → topics → summaries",
        ], label="OPERATIONS")

        footer_y = self.y + 30
        footer_h = 76
        self.draw.rounded_rectangle((52, footer_y, WIDTH - 52, footer_y + footer_h),
                                    radius=7, fill=CALLOUT, outline=INK, width=2)
        self._svg_rect(52, footer_y, WIDTH - 104, footer_h,
                       self._hex(CALLOUT), stroke=INK, sw=2, rx=7)
        self.text(WIDTH // 2, footer_y + 25,
                  "PIPELINE ORDER FROM scripts/run_pipeline.sh AND run_semantics_and_ner.sh",
                  F_PILL, fill=BODY, anchor="mm")
        self.text(WIDTH // 2, footer_y + 52,
                  "Model training is an optional offline branch; serving uses persisted summaries and entities.",
                  F_SUBTITLE, fill=BODY, anchor="mm")
        self.y = footer_y + footer_h + 34
        self.save()

    def save(self):
        self.image = self.image.crop((0, 0, WIDTH, self.y))
        self.image.save(PNG_PATH, format="PNG", optimize=True)
        svg_doc = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{self.y}" viewBox="0 0 {WIDTH} {self.y}">',
            f'<rect width="{WIDTH}" height="{self.y}" fill="{self._hex(PAGE)}"/>',
            *self.svg,
            "</svg>",
        ]
        SVG_PATH.write_text("\n".join(svg_doc), encoding="utf-8")
        print(f"PNG: {PNG_PATH}")
        print(f"SVG: {SVG_PATH}")
        print(f"Size: {WIDTH} x {self.y}")


if __name__ == "__main__":
    Diagram().build()
