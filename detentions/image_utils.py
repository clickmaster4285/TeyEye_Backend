"""Image compression and optimization utilities for detention memo uploads."""

import io
from PIL import Image
from django.core.files.uploadedfile import InMemoryUploadedFile


def compress_image(
    uploaded_file,
    max_width: int = 1920,
    max_height: int = 1080,
    quality: int = 85,
    format: str = "JPEG",
) -> InMemoryUploadedFile:
    """
    Compress and resize an uploaded image.

    Args:
        uploaded_file: Django UploadedFile object
        max_width: Maximum width in pixels
        max_height: Maximum height in pixels
        quality: JPEG quality (1-100)
        format: Output format (JPEG, PNG, WEBP)

    Returns:
        Compressed InMemoryUploadedFile
    """
    try:
        # Open the image
        img = Image.open(uploaded_file)

        # Convert RGBA to RGB if needed (for JPEG)
        if img.mode in ("RGBA", "LA", "P"):
            rgb_img = Image.new("RGB", img.size, (255, 255, 255))
            rgb_img.paste(img, mask=img.split()
                          [-1] if img.mode == "RGBA" else None)
            img = rgb_img

        # Resize while maintaining aspect ratio
        img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

        # Save to bytes buffer
        output = io.BytesIO()
        img.save(output, format=format, quality=quality, optimize=True)
        output.seek(0)

        # Create new uploaded file object
        filename = f"{uploaded_file.name.rsplit('.', 1)[0]}.{format.lower()}"
        compressed_file = InMemoryUploadedFile(
            file=output,
            field_name=uploaded_file.field_name,
            name=filename,
            content_type=f"image/{format.lower()}",
            size=output.getbuffer().nbytes,
            charset=None,
        )

        return compressed_file

    except Exception as e:
        # If compression fails, return original file
        print(f"Image compression failed: {str(e)}")
        return uploaded_file
