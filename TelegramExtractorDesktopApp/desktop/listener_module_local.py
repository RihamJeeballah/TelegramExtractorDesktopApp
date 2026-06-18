# desktop/listener_module.py
from telethon import events
from datetime import datetime
from desktop.exporter_module import append_row   # ✅ use append_row instead of save_to_excel
from desktop.extractor_module import extract_fields


async def start_listener(client, chat_ids, output_callback=None):
    """Run the async listener for selected groups."""

    @client.on(events.NewMessage(chats=chat_ids))
    async def handler(event):
        try:
            text = event.raw_text or ""
            if output_callback:
                output_callback(f"📩 {text}")

            # Extract fields from the message
            result = extract_fields(text)
            result["timestamp"] = event.date.replace(tzinfo=None)
            result["raw_message"] = text

            # ✅ Append to Excel (instead of overwriting)
            append_row(result)

            if output_callback:
                output_callback("✅ Extracted & saved.\n")
        except Exception as e:
            if output_callback:
                output_callback(f"⚠️ Error: {e}\n")

    if output_callback:
        output_callback(f"👂 Listening to {len(chat_ids)} group(s)...")

    await client.run_until_disconnected()
