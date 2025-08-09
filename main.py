# main.py

# --- IMPORTS ---
from fastapi import FastAPI, File, UploadFile, Form, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.colormasks import SolidFillColorMask
import io  
from PIL import Image, ImageColor
import os
from qrcode.image.styles.moduledrawers import GappedSquareModuleDrawer, RoundedModuleDrawer, CircleModuleDrawer

# --- CONFIGURATION ---
RAPIDAPI_PROXY_SECRET = os.getenv("RAPIDAPI_PROXY_SECRET", "THIS_IS_MY_SECRET_KEY_12345")
# NEW: Define a minimum contrast ratio for scannability
MIN_CONTRAST_RATIO = 4.5 

# --- SECURITY DEPENDENCY ---
async def verify_secret(x_rapidapi_proxy_secret: str = Header(None)):
    if not x_rapidapi_proxy_secret or x_rapidapi_proxy_secret != RAPIDAPI_PROXY_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid or missing secret key.")
    return x_rapidapi_proxy_secret

# --- NEW HELPER FUNCTIONS for COLOR VALIDATION ---
def get_relative_luminance(rgb):
    """Calculates relative luminance for an RGB color."""
    r, g, b = [x / 255.0 for x in rgb]
    r = r / 12.92 if r <= 0.03928 else ((r + 0.055) / 1.055) ** 2.4
    g = g / 12.92 if g <= 0.03928 else ((g + 0.055) / 1.055) ** 2.4
    b = b / 12.92 if b <= 0.03928 else ((b + 0.055) / 1.055) ** 2.4
    return 0.2126 * r + 0.7152 * g + 0.0822 * b

def check_color_contrast(color1_rgb, color2_rgb):
    """Checks if two colors have enough contrast and are not inverted."""
    lum1 = get_relative_luminance(color1_rgb)
    lum2 = get_relative_luminance(color2_rgb)

    # Ensure fill color is darker than background color
    if lum1 > lum2:
        raise HTTPException(
            status_code=400,
            detail=f"Color Error: Fill color must be darker than the background color for scannability."
        )

    # Calculate contrast ratio
    ratio = (lum2 + 0.05) / (lum1 + 0.05)
    if ratio < MIN_CONTRAST_RATIO:
        raise HTTPException(
            status_code=400,
            detail=f"Low Contrast Error: The contrast ratio between colors is {ratio:.2f}:1. It must be at least {MIN_CONTRAST_RATIO}:1 to be scannable. Please choose a darker fill color or a lighter background."
        )

# --- FASTAPI APP ---
app = FastAPI(
    title="Custom QR Code API",
    description="A professional-grade API to create custom QR codes with logos.",
    version="1.0.0",
    dependencies=[Depends(verify_secret)]
)

# --- ENDPOINTS ---
# (The basic endpoint remains the same)
@app.get("/generate-basic/", response_class=StreamingResponse, tags=["QR Code Generation"])
def generate_basic_qr_code(url: str):
    """
    Generates a basic, black-and-white QR code for the given URL.
    """
     

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
    module_style: str = Form("square", enum=["square", "rounded", "dot"]), # NEW PARAMETER
):
    """
    Generates a custom QR code. 
    
    - **url**: The URL to encode.
    - **logo_file**: The logo image file (e.g., PNG, JPG) to embed.
    - **fill_color**: The color of the QR code modules (e.g., 'black', '#FF5733').
    - **back_color**: The background color of the QR code.
    - **module_style**: The shape of the data modules: 'square', 'rounded', or 'dot'.
    """

    # --- Color Conversion and VALIDATION ---
    try:
        fill = ImageColor.getcolor(fill_color, "RGB")
        back = ImageColor.getcolor(back_color, "RGB")
        check_color_contrast(fill, back)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid color name provided.")
    except HTTPException as e:
        raise e # Re-raise the contrast error

 # --- NEW: Select the module drawer based on input ---
    if module_style == "rounded":
        drawer = RoundedModuleDrawer()
    elif module_style == "dot":
        drawer = CircleModuleDrawer()
    else:
        drawer = GappedSquareModuleDrawer()

   # --- Create the high-error-correction QR code ---
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
    qr.add_data(url)

    # --- Create the QR code image with custom colors AND style ---
    qr_img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=drawer, # USE THE SELECTED DRAWER
        color_mask=SolidFillColorMask(front_color=fill, back_color=back)
    )

    # (The rest of the function is identical)
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

    