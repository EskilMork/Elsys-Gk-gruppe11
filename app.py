import os
import shutil
import sys
import threading
import uuid
from enum import Enum
from pathlib import Path
from time import sleep
from typing import Optional

import pygame
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from polls_db import (
    fetch_all_polls,
    fetch_poll_by_caption,
    fetch_poll,
    init_db,
    save_poll_record,
    update_image_path,
)

BASE_DIR = Path(__file__).resolve().parent
MEDIA_DIR = BASE_DIR / "media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)


class DisplayMode(Enum):
    RESULTS = "results"
    IMAGE = "image"


def normalize_image_path(path_str: Optional[str]) -> Optional[str]:
    if not path_str:
        return None
    candidate = Path(path_str).expanduser()
    if not candidate.is_absolute():
        candidate = (BASE_DIR / candidate).resolve()
    else:
        candidate = candidate.resolve()
    if not candidate.exists():
        raise FileNotFoundError(candidate)
    try:
        return str(candidate.relative_to(BASE_DIR))
    except ValueError:
        return str(candidate)


def absolute_image_path(stored_path: Optional[str]) -> Optional[Path]:
    if not stored_path:
        return None
    candidate = Path(stored_path)
    if not candidate.is_absolute():
        candidate = (BASE_DIR / candidate).resolve()
    else:
        candidate = candidate.resolve()
    return candidate

os.environ.setdefault('SDL_VIDEODRIVER', 'kmsdrm')

DISABLE_GPIO = os.environ.get("DISABLE_GPIO") == "1"
RUN_DISPLAY = os.environ.get("DISABLE_DISPLAY") != "1"

if not DISABLE_GPIO:
    try:
        from gpiozero import Button
    except Exception as gpio_exc:  # pragma: no cover - dev convenience
        print(f"GPIO unavailable ({gpio_exc}); running without hardware buttons.")
        DISABLE_GPIO = True
        Button = None  # type: ignore
else:
    Button = None  # type: ignore

# -------------------------
# GPIO Button Setup
# -------------------------
yes_count = 0
no_count =  0
meh_count = 0

if not DISABLE_GPIO and Button:
    button_yes = Button(16, bounce_time=0.04)
    button_no = Button(26, bounce_time=0.04)
    button_meh = Button(12, bounce_time=0.04)
else:
    button_yes = button_no = button_meh = None
combo_toggle_active = False

def add_one_yes():
    global yes_count
    yes_count += 1
    print("YES:", yes_count)

def add_one_no():
    global no_count
    no_count += 1
    print("NO:", no_count)
    
def add_one_meh():
    global meh_count
    meh_count += 1
    print("MEH", meh_count)

if button_yes:
    button_yes.when_released = add_one_yes
if button_no:
    button_no.when_pressed = add_one_no
if button_meh:
    button_meh.when_pressed = add_one_meh

# -------------------------
# Pygame Setup
# -------------------------

score_a = 40 
score_b = 20
score_meh = 10
current_display_mode = DisplayMode.RESULTS
current_image_surface = None
loaded_image_path = None


def mark_image_dirty():
    global loaded_image_path
    loaded_image_path = None


def toggle_display_mode(explicit: Optional[DisplayMode] = None):
    global current_display_mode
    if explicit:
        current_display_mode = explicit
    else:
        current_display_mode = (
            DisplayMode.IMAGE
            if current_display_mode == DisplayMode.RESULTS
            else DisplayMode.RESULTS
        )
    print(f"Visningsmodus: {current_display_mode.value}")


def check_button_combo_toggle():
    """Toggle display mode if all three hardware buttons are pressed simultaneously."""
    global combo_toggle_active
    if not all([button_yes, button_no, button_meh]):
        return

    pressed = button_yes.is_pressed and button_no.is_pressed and button_meh.is_pressed
    if pressed and not combo_toggle_active:
        combo_toggle_active = True
        toggle_display_mode()
    elif not pressed and combo_toggle_active:
        combo_toggle_active = False

init_db()
# -------------------------
# Shared data mellom FastAPI og Pygame
# -------------------------
shared_data = {
    "id": uuid.uuid4().hex[:8],
    "caption": "Live Duel",  # default caption
    "score_a": score_a,
    "score_b": score_b,
    "score_meh": score_meh,
    "image_path": None,
}

last_persisted_poll = {
    "id": None,
    "caption": None,
    "score_a": None,
    "score_b": None,
    "score_meh": None,
    "image_path": None,
}

existing_polls = fetch_all_polls()
if existing_polls:
    latest_poll = existing_polls[0]
    shared_data.update(latest_poll)
    shared_data.setdefault("image_path", None)
    yes_count = latest_poll["score_a"]
    no_count = latest_poll["score_b"]
    meh_count = latest_poll["score_meh"]
    score_a = yes_count
    score_b = no_count
    score_meh = meh_count
    for key in last_persisted_poll:
        last_persisted_poll[key] = latest_poll.get(key)

# -------------------------
# FastAPI Setup
# -------------------------
app = FastAPI(title="Caption & Score API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

return_data = {
    "id": 1, 
    "navn": "caption",
    "score_a": score_a,
    "score_b": score_b,
    "score_meh": score_meh
}


def save_poll(force: bool = False):
    poll_copy = {
        "id": shared_data.get("id"),
        "caption": shared_data.get("caption"),
        "score_a": shared_data.get("score_a", 0),
        "score_b": shared_data.get("score_b", 0),
        "score_meh": shared_data.get("score_meh", 0),
        "image_path": shared_data.get("image_path")
    }
    poll_id = poll_copy["id"]
    if not poll_id:
        return

    has_changed = any(
        last_persisted_poll.get(key) != poll_copy.get(key)
        for key in last_persisted_poll
    )
    if not force and not has_changed:
        return

    save_poll_record(poll_copy)
    last_persisted_poll.update(poll_copy)


def find_poll(poll_id: str):
    """Hent en poll ut fra id."""
    return fetch_poll(poll_id)


def resolve_poll_target(poll_id: Optional[str], poll_name: Optional[str]):
    poll = None
    resolved_id = None
    if poll_id:
        poll = find_poll(poll_id)
        if poll:
            resolved_id = poll["id"]
            return poll, resolved_id
    if poll_name:
        poll = fetch_poll_by_caption(poll_name)
        if poll:
            resolved_id = poll["id"]
            return poll, resolved_id
    return None, None


class Caption(BaseModel):
    id: str
    text: str = "skriv inn en poll her"
    name: Optional[str] = None


class ImageAttachment(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    image_path: Optional[str] = None

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")

@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.post("/update_caption/")
def update_caption(caption: Caption):
    global yes_count, no_count, meh_count
    print("id cap", caption.id)

    incoming_id = (caption.id or "").strip() or uuid.uuid4().hex[:8]
    current_id = shared_data.get("id")
    is_new_request = bool(caption.name)

    if current_id == incoming_id:
        shared_data["caption"] = caption.text
        shared_data["score_a"] = yes_count
        shared_data["score_b"] = no_count
        shared_data["score_meh"] = meh_count
        save_poll(force=True)
        return {"message": "Oppdatert aktiv poll", "data": shared_data}

    if current_id and current_id != incoming_id:
        save_poll(force=True)

    existing = find_poll(incoming_id)
    if existing:
        result = update_old_polls(incoming_id)
        if caption.text and caption.text != shared_data["caption"]:
            shared_data["caption"] = caption.text
            save_poll(force=True)
            result["data"]["caption"] = caption.text
        return result
    if not is_new_request:
        raise HTTPException(status_code=404, detail=f"Poll {incoming_id} finnes ikke i databasen.")

    # 🔹 deretter oppdater ny poll
    shared_data["caption"] = caption.text
    shared_data["id"] = incoming_id
    shared_data["image_path"] = None
    mark_image_dirty()

    yes_count = no_count = meh_count = 0
    shared_data["score_a"] = yes_count
    shared_data["score_b"] = no_count
    shared_data["score_meh"] = meh_count

    save_poll(force=True)

    # 🔹 do NOT save again here
    return {"message": "Ny caption lagret!", "data": shared_data}


@app.post("/attach_image/")
def attach_image(payload: ImageAttachment):
    target_poll, target_id = resolve_poll_target(payload.id, payload.name)
    if not target_poll or not target_id:
        identifier = payload.id or payload.name or "<ukjent>"
        raise HTTPException(status_code=404, detail=f"Poll '{identifier}' finnes ikke.")

    normalized_path = None
    if payload.image_path:
        try:
            normalized_path = normalize_image_path(payload.image_path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=f"Bilde ikke funnet: {exc}")

    update_image_path(target_id, normalized_path)
    target_poll["image_path"] = normalized_path

    if shared_data.get("id") == target_id:
        shared_data["image_path"] = normalized_path
        mark_image_dirty()
        save_poll(force=True)

    return {"message": "Oppdatert bilde for poll", "data": target_poll}


def store_uploaded_image(poll_id: str, upload: UploadFile) -> str:
    if not upload.filename:
        raise HTTPException(status_code=400, detail="Filen mangler navn.")
    if upload.content_type and not upload.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Kun bildefiler er tillatt.")

    suffix = Path(upload.filename).suffix.lower() or ".png"
    dest_dir = MEDIA_DIR / poll_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{suffix}"
    target_path = dest_dir / filename

    upload.file.seek(0)
    with target_path.open("wb") as out_file:
        shutil.copyfileobj(upload.file, out_file)

    return str(target_path.relative_to(BASE_DIR))


@app.post("/upload_image/")
async def upload_image(
    file: UploadFile = File(...),
    poll_id: Optional[str] = Form(None),
    poll_name: Optional[str] = Form(None),
):
    target_poll, target_id = resolve_poll_target(poll_id, poll_name)
    if not target_poll or not target_id:
        identifier = poll_id or poll_name or "<ukjent>"
        raise HTTPException(status_code=404, detail=f"Poll '{identifier}' finnes ikke.")

    relative_path = store_uploaded_image(target_id, file)
    update_image_path(target_id, relative_path)
    target_poll["image_path"] = relative_path

    if shared_data.get("id") == target_id:
        shared_data["image_path"] = relative_path
        mark_image_dirty()
        save_poll(force=True)

    return {"message": "Bilde lastet opp", "data": target_poll}

# @app.post("/update_caption/")
#def update_caption(caption: Caption):
#    print("id cap", caption.id)
#    print("exsistin", old_polls)
#    existing = find_poll(caption.id)
#    if existing:
#        return update_old_polls(caption.id)
#
#    # 🔹 lagre forrige poll først (hvis den finnes)
#    if shared_data.get("id"):
#        save_poll()
#
#    # 🔹 deretter oppdater ny poll
#    shared_data["caption"] = caption.text
#    shared_data["id"] = caption.id
#
#    global yes_count, no_count, meh_count
#    yes_count = no_count = meh_count = 0
#
#    save_poll()  # lagre også den nye etter oppdatering
#    return {"message": "Ny caption lagret!", "data": shared_data}




@app.get("/get_scores/")
def get_scores():
    return {
        "score_a": shared_data["score_a"],
        "score_b": shared_data["score_b"],
        "score_meh": shared_data["score_meh"],
        "id": shared_data["id"],
        "image_path": shared_data.get("image_path"),
    }

@app.get("/get_old_polls")
def get_old_polls(): 
    return fetch_all_polls()

def update_old_polls(id: str):
    poll = find_poll(id)
    if not poll:
        return {"error": "Poll ikke funnet"}

    global shared_data, yes_count, no_count, meh_count
    shared_data = poll.copy()
    shared_data.setdefault("image_path", None)

    yes_count = shared_data["score_a"]
    no_count = shared_data["score_b"]
    meh_count = shared_data["score_meh"]
    for key in last_persisted_poll:
        last_persisted_poll[key] = shared_data.get(key)
    mark_image_dirty()

    return {"message": "Gjenopptok gammel poll", "data": shared_data}

                

def run_api():
    uvicorn.run(app, host="0.0.0.0", port=8000)


# Start FastAPI i egen tråd
threading.Thread(target=run_api, daemon=True).start()

if RUN_DISPLAY:
    # -------------------------
    # Hovedløkken til Pygame
    # -------------------------

    pygame.init()

    # --- skjermoppsett ---
    WIDTH, HEIGHT = 1920, 1080
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
    pygame.display.set_caption("Live Duel")

    # --- farger ---
    BG = (15, 18, 30)
    YES_COLOR = (47, 204,113)
    NO_COLOR = (255, 80, 60)
    MEH_COLOR = (240, 200,0 )
    TEXT_COLOR = (255, 255, 255)
    GRID_COLOR = (60, 65, 80)

    # --- fonter ---
    font_large = pygame.font.Font(None, int(HEIGHT * 0.1))
    font_small = pygame.font.Font(None, int(HEIGHT * 0.05))

    clock = pygame.time.Clock()
    running = True

    # --- layout ---
    CATEGORIES = [
        ("YES", YES_COLOR),
        ("MEH", MEH_COLOR),
        ("NO", NO_COLOR)
    ]

    MARGIN_X = WIDTH * 0.1
    SPACING = (WIDTH - 2 * MARGIN_X) / len(CATEGORIES)
    BAR_WIDTH = SPACING * 0.4
    BOTTOM_MARGIN = HEIGHT * 0.2
    font_hint = pygame.font.Font(None, int(HEIGHT * 0.035))

    def ensure_image_surface_loaded():
        global current_image_surface, loaded_image_path
        target_path = shared_data.get("image_path")
        if target_path == loaded_image_path:
            return
        loaded_image_path = target_path
        if not target_path:
            current_image_surface = None
            return
        absolute = absolute_image_path(target_path)
        if not absolute or not absolute.exists():
            current_image_surface = None
            return
        try:
            current_image_surface = pygame.image.load(str(absolute)).convert()
        except Exception as exc:
            print(f"Kunne ikke laste bilde {absolute}: {exc}")
            current_image_surface = None

    def draw_results_view():
        max_score = max(score_a, score_b, score_meh, 1)
        scores = [score_a, score_meh, score_b]

        screen.fill(BG)
        for i in range(6):
            y = HEIGHT - BOTTOM_MARGIN - (i * (HEIGHT * 0.6 / 5))
            pygame.draw.line(screen, GRID_COLOR, (MARGIN_X * 0.8, y), (WIDTH - MARGIN_X * 0.8, y), 1)

        for i, (label, color) in enumerate(CATEGORIES):
            x_center = MARGIN_X + i * SPACING + SPACING / 2
            score_value = scores[i]
            bar_height = (score_value / max_score) * (HEIGHT * 0.6)
            rect = pygame.Rect(0, 0, BAR_WIDTH, bar_height)
            rect.centerx = x_center
            rect.bottom = HEIGHT - BOTTOM_MARGIN
            pygame.draw.rect(screen, color, rect, border_radius=20)

            txt_value = font_large.render(str(score_value), True, TEXT_COLOR)
            screen.blit(txt_value, (x_center - txt_value.get_width()/2, rect.top - txt_value.get_height() - 10))

            txt_label = font_small.render(label, True, TEXT_COLOR)
            screen.blit(txt_label, (x_center - txt_label.get_width()/2, HEIGHT - BOTTOM_MARGIN + 20))

        caption_text = font_small.render(shared_data["caption"], True, TEXT_COLOR)
        screen.blit(caption_text, (WIDTH/2 - caption_text.get_width()/2, HEIGHT - caption_text.get_height() - 10))

    def draw_image_view():
        ensure_image_surface_loaded()
        screen.fill(BG)

        if current_image_surface:
            img = current_image_surface
            img_w, img_h = img.get_size()
            max_w = WIDTH * 0.9
            max_h = HEIGHT * 0.8
            scale = min(max_w / img_w, max_h / img_h)
            scale = max(scale, 0.1)
            target_size = (int(img_w * scale), int(img_h * scale))
            if target_size[0] > 0 and target_size[1] > 0:
                if target_size != (img_w, img_h):
                    display_img = pygame.transform.smoothscale(img, target_size)
                else:
                    display_img = img
                rect = display_img.get_rect(center=(WIDTH/2, HEIGHT/2))
                screen.blit(display_img, rect)
        else:
            msg = "Ingen bilde knyttet til denne pollen"
            placeholder = font_small.render(msg, True, TEXT_COLOR)
            screen.blit(placeholder, (WIDTH/2 - placeholder.get_width()/2, HEIGHT/2 - placeholder.get_height()/2))

        caption_text = font_small.render(shared_data["caption"], True, TEXT_COLOR)
        screen.blit(caption_text, (WIDTH/2 - caption_text.get_width()/2, HEIGHT - caption_text.get_height() - 10))

    def draw_mode_hint():
        hint_text = "Trykk alle knappene samtidig for å bytte bilde!"
        hint = font_hint.render(hint_text, True, TEXT_COLOR)
        screen.blit(hint, (MARGIN_X * 0.1, 20))

    while running:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False
                elif e.key == pygame.K_y:
                    yes_count += 1
                elif e.key == pygame.K_m:
                    meh_count += 1
                elif e.key == pygame.K_n:
                    no_count += 1
                elif e.key == pygame.K_p:
                    toggle_display_mode()
                elif e.key == pygame.K_r:
                    toggle_display_mode(DisplayMode.RESULTS)
                elif e.key == pygame.K_i:
                    toggle_display_mode(DisplayMode.IMAGE)

        check_button_combo_toggle()

        # --- oppdater score fra GPIO-knapper ---
        score_a = yes_count
        score_b = no_count
        score_meh = meh_count
        shared_data["score_a"] = score_a
        shared_data["score_b"] = score_b
        shared_data["score_meh"] = score_meh
        save_poll()

        if current_display_mode == DisplayMode.RESULTS:
            draw_results_view()
        else:
            draw_image_view()

        draw_mode_hint()

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
else:
    print("Display disabled; keeping API thread alive.")
    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        pass
