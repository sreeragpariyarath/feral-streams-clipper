import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock

from src.media.transcription import _transcribe_audio_chunks


class WhisperChunksTest(unittest.TestCase):
    def test_partial_last_chunk_and_absolute_word_times(self):
        def transcript(samples, **options):
            return {"text": "hello", "language": "en", "segments": [
                {"start": 0.0, "end": 0.2, "words": [{"start": 0.1, "end": 0.2}]}
            ]}

        model = Mock()
        model.transcribe.side_effect = transcript
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.wav"
            with wave.open(str(source), "wb") as wav:
                wav.setparams((1, 2, 16000, 0, "NONE", ""))
                wav.writeframes(bytes(40000))
            result = _transcribe_audio_chunks(model, source, None, chunk_seconds=1)
        calls = model.transcribe.call_args_list
        self.assertEqual([len(call.args[0]) for call in calls], [16000, 4000])
        self.assertEqual(calls[1].kwargs["language"], "en")
        self.assertEqual(result["segments"][1]["words"][0]["start"], 1.1)
        self.assertEqual(result["segments"][1]["end"], 1.2)
        self.assertEqual(result["text"], "hello hello")


if __name__ == "__main__":
    unittest.main()
