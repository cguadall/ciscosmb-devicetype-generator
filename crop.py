import os
from PIL import Image

def crop_transparent_png(input_path):
    """
    1st Pass:
    Crops a transparent PNG so that only the non-transparent pixels remain.
    Returns an Image object (RGBA).
    """
    img = Image.open(input_path)

    # Ensure image is in RGBA mode (has an alpha channel)
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    # Extract the alpha channel
    alpha = img.getchannel("A")

    # Get the bounding box of non-transparent (non-zero) pixels in the alpha channel
    bbox = alpha.getbbox()

    if bbox:
        # Crop the image to that bounding box
        img = img.crop(bbox)
    # If bbox is None, the image is fully transparent - keep as is, or handle accordingly
    return img


def enforce_10_to_1_aspect(img):
    """
    2nd Pass:
    Ensures the image is exactly 10:1 (width:height), maintaining the same height.
    Align to left, fill with white (or crop) on the right.
    
    Returns a new Image object in RGB mode with a white background.
    """
    # Convert to RGBA if not already, to handle potential alpha
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    width, height = img.size
    target_width = int(10 * height)  # Exact 10:1 aspect ratio

    # Create a new image in "RGB" with a white background
    #   for the final output (since we want white padding).
    if width == target_width:
        # Already 10:1, just flatten to white background
        final_img = Image.new("RGB", (width, height), (255, 255, 255))
        final_img.paste(img, (0, 0), mask=img)
        return final_img
    elif width < target_width:
        # Need to add white padding on the right
        final_img = Image.new("RGB", (target_width, height), (255, 255, 255))
        final_img.paste(img, (0, 0), mask=img)
        return final_img
    else:
        # width > target_width, crop from the right to enforce 10:1
        cropped_img = img.crop((0, 0, target_width, height))
        # Flatten to white background
        final_img = Image.new("RGB", (target_width, height), (255, 255, 255))
        final_img.paste(cropped_img, (0, 0), mask=cropped_img)
        return final_img


def process_image(input_path, output_path):
    """
    Performs both passes on a single file:
      1) Crop transparent borders
      2) Enforce 10:1 aspect ratio with white padding/cropping
    Then saves to output_path.
    """
    # 1) Crop transparent regions
    cropped_img = crop_transparent_png(input_path)

    # 2) Enforce 10:1 aspect ratio
    final_img = enforce_10_to_1_aspect(cropped_img)

    # Save result
    final_img.save(output_path)
    print(f"Saved final 10:1 image to: {output_path}")


def process_directory(directory_path, overwrite=True):
    """
    Processes all PNG files in the given directory:
      - Crops transparent areas
      - Enforces 10:1 aspect ratio
    Overwrites the original files if overwrite=True,
    otherwise saves with 'final_' prefix.
    """
    directory_path = os.path.abspath(directory_path)
    
    for filename in os.listdir(directory_path):
        if filename.lower().endswith(".png"):
            input_file = os.path.join(directory_path, filename)

            if overwrite:
                output_file = input_file
            else:
                name_part, ext = os.path.splitext(filename)
                new_name = f"final_{name_part}{ext}"
                output_file = os.path.join(directory_path, new_name)

            process_image(input_file, output_file)


if __name__ == "__main__":
    # Path to your directory containing PNGs
    directory = "front-rear"
    process_directory(directory, overwrite=True)
