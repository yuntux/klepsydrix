import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import generate_demo as gd

DURATIONS = {s["id"]: 4.0 for s in gd.script_segments}


async def main():
    video_path, timestamps = await gd.capture(DURATIONS)
    print("VIDEO_PATH:", video_path)
    print("TIMESTAMPS:", timestamps)
    (Path(__file__).parent / "_test_timestamps.txt").write_text(
        f"{video_path}\n" + "\n".join(f"{k} {v:.2f}" for k, v in timestamps.items())
    )


asyncio.run(main())
