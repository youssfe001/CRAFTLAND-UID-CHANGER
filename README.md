# Craftland UID Hex Editor

A lightweight, single-page web app for inspecting and editing Craftland UID values inside `.bytes` files. Everything runs locally in your browser—no uploads, no server required.

**Website name:** Craftland UID Hex Editor
**Website URL:** https://auron-uid-changer-0254.vercel.app/

## Features

- Drag & drop `.bytes` files or browse to upload.
- Detects the Craftland UID and shows its offset.
- Highlights the UID bytes in a hex preview window.
- Update or clear the UID and export the modified file instantly.

## How It Works (Short)

The app scans for the UID marker (`0x38`), decodes a varint UID, verifies the trailing marker (`0x42`), and then lets you replace the UID while keeping the rest of the file intact.

## License

No license specified. Add a license if you want to define usage terms.
