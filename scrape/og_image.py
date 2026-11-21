"""Draw the social preview card (site/og.png, 1200x630) from site/data.js: the current top five teams."""
import os, json
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS_BOLD = ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"]
FONTS = ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf"]


def font(paths, size):
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def main():
    s = open(os.path.join(ROOT, "site", "data.js"), encoding="utf8").read()
    d = json.loads(s[s.index("{"):s.rindex("}") + 1])
    teams = sorted((t for t in d["teams"] if t["indian"] and not t.get("gc") and t.get("active")), key=lambda t: -t["rating"])[:5]
    W, H = 1200, 630
    bg, panel, fg, muted, acc = (14, 16, 22), (21, 24, 33), (233, 231, 225), (141, 146, 163), (240, 166, 58)
    im = Image.new("RGB", (W, H), bg)
    dr = ImageDraw.Draw(im)
    dr.polygon([(64, 64), (100, 64), (100, 86), (86, 100), (64, 100)], fill=acc)
    dr.text((120, 58), "Indian Valorant Index", font=font(FONTS_BOLD, 44), fill=fg)
    dr.text((66, 130), "Team rankings · player stats · head-to-heads · every event since 2020", font=font(FONTS, 26), fill=muted)
    dr.rounded_rectangle((60, 190, W - 60, 560), radius=10, fill=panel)
    dr.text((90, 210), f"TOP TEAMS · DATA TO {d['generated']}", font=font(FONTS_BOLD, 22), fill=muted)
    f_rank, f_name, f_rt = font(FONTS_BOLD, 40), font(FONTS_BOLD, 36), font(FONTS_BOLD, 36)
    for i, t in enumerate(teams):
        y = 258 + i * 58
        dr.text((92, y), str(i + 1), font=f_rank, fill=acc if i < 3 else muted)
        dr.text((150, y + 3), t["name"][:34], font=f_name, fill=fg)
        rt = str(t["rating"])
        dr.text((W - 92 - dr.textlength(rt, font=f_rt), y + 3), rt, font=f_rt, fill=fg)
    dr.text((66, 580), "alan-r-henry.github.io/indian-valorant-index · data from VLR.gg and Liquipedia", font=font(FONTS, 22), fill=muted)
    im.save(os.path.join(ROOT, "site", "og.png"), optimize=True)
    print("og.png written")


if __name__ == "__main__":
    main()
