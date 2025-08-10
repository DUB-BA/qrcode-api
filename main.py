# main.py

# --- IMPORTS ---
from fastapi import FastAPI, File, UploadFile, Form, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware  # <-- Correctly imported
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.colormasks import SolidFillColorMask
import io
from PIL import Image, ImageColor
import os
from qrcode.image.styles.moduledrawers import GappedSquareModuleDrawer, RoundedModuleDrawer, CircleModuleDrawer


# --- CONFIGURATION ---
RAPIDAPI_PROXY_SECRET = os.getenv("RAPIDAPI_PROXY_SECRET", "sUp3r-S3cr3t-Qu33n-b33-K3y-9z8y") # I updated the default here for safety
MIN_CONTRAST_RATIO = 4.5

# --- SECURITY DEPENDENCY ---
async def verify_secret(x_api_secret: str = Header(None, alias="X-API-Secret")):
    if not x_api_secret or x_api_secret != RAPIDAPI_PROXY_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid or missing secret key.")
    return x_api_secret

# --- HELPER FUNCTIONS ---
def get_relative_luminance(rgb):
    r, g, b = [x / 255.0 for x in rgb]
    r = r / 12.92 if r <= 0.03928 else ((r + 0.055) / 1.055) ** 2.4
    g = g / 12.92 if g <= 0.03928 else ((g + 0.055) / 1.055) ** 2.4
    b = b / 12.92 if b <= 0.03928 else ((b + 0.055) / 1.055) ** 2.4
    return 0.2126 * r + 0.7152 * g + 0.0822 * b

def check_color_contrast(color1_rgb, color2_rgb):
    lum1 = get_relative_luminance(color1_rgb)
    lum2 = get_relative_luminance(color2_rgb)
    if lum1 > lum2:
        raise HTTPException(status_code=400, detail="Color Error: Fill color must be darker than the background color.")
    ratio = (lum2 + 0.05) / (lum1 + 0.05)
    if ratio < MIN_CONTRAST_RATIO:
        raise HTTPException(status_code=400, detail=f"Low Contrast Error: Contrast ratio is {ratio:.2f}:1. Must be at least {MIN_CONTRAST_RATIO}:1.")

# --- FASTAPI APP INITIALIZATION ---
app = FastAPI(
    title="Custom QR Code API",
    description="A professional-grade API to create custom QR codes with logos.",
    version="1.1.0", # Bumped version for the new feature
    dependencies=[Depends(verify_secret)]
)

# --- ADD CORS MIDDLEWARE ---
# This is the new block that fixes the browser testing issue.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# --- API ENDPOINTS ---
@app.get("/generate-basic/", response_class=StreamingResponse, tags=["QR Code Generation"])
def generate_basic_qr_code(url: str):
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

@app.post("/generate-custom/", response_class=StreamingResponse, tags=["QR Code Generation"])
def generate_custom_qr_code(
    url: str = Form(...),
    logo_file: UploadFile = File(...),
    fill_color: str = Form("black"),
    back_color: str = Form("white"),
    module_style: str = Form("square", enum=["square", "rounded", "dot"]),
):
    try:
        fill = ImageColor.getcolor(fill_color, "RGB")
        back = ImageColor.getcolor(back_color, "RGB")
        check_color_contrast(fill, back)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid color name provided.")
    except HTTPException as e:
        raise e

    if module_style == "rounded":
        drawer = RoundedModuleDrawer()
    elif module_style == "dot":
        drawer = CircleModuleDrawer()
    else:
        drawer = GappedSquareModuleDrawer()

    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
    qr.add_data(url)

    qr_img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=drawer,
        color_mask=SolidFillColorMask(front_color=fill, back_color=back)
    )

    logo_img = Image.open(logo_file.file).convert("RGBA")
    qr_width, qr_height = qr_img.size
    logo_max_size = qr_width // 4
    logo_img.thumbnail((logo_max_size, logo_max_size))
    pos = ((qr_width - logo_img.size[0]) // 2, (qr_height - logo_img.size[1]) // 2)
    qr_img.paste(logo_img, pos, mask=logo_img)

    buf = io.BytesIO()
    qr_img.save(buf, "PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

# --- SERVER RUN COMMAND ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))