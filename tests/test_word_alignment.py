from pathlib import Path
import httpx
import pytest

from app.studio.adapters.alignment import WordAlignmentService
from app.studio.domain.captions import WordTiming


class TestNativeWordAlignment:
    def test_empty_or_whitespace_text_returns_empty_list(self):
        service = WordAlignmentService()
        assert service.align_words("", 1000) == []
        assert service.align_words("   \n\t  ", 1000) == []

    def test_zero_or_negative_duration_returns_empty_list(self):
        service = WordAlignmentService()
        assert service.align_words("palavra", 0) == []
        assert service.align_words("palavra", -500) == []

    def test_single_word_spans_full_duration(self):
        service = WordAlignmentService()
        timings = service.align_words("Unica!", 1500)
        assert len(timings) == 1
        assert timings[0].word == "Unica!"
        assert timings[0].start_ms == 0
        assert timings[0].duration_ms == 1500

    def test_exact_boundary_guarantees(self):
        service = WordAlignmentService()
        text = "Esta é uma frase de teste com várias palavras."
        audio_duration_ms = 3500

        timings = service.align_words(text, audio_duration_ms)
        words = text.split()

        assert len(timings) == len(words)
        assert timings[0].start_ms == 0

        for i, timing in enumerate(timings):
            assert timing.word == words[i]
            assert timing.start_ms >= 0
            assert timing.duration_ms > 0
            assert timing.start_ms + timing.duration_ms <= audio_duration_ms
            if i > 0:
                assert timing.start_ms == timings[i - 1].start_ms + timings[i - 1].duration_ms

        assert timings[-1].start_ms + timings[-1].duration_ms == audio_duration_ms
        assert sum(t.duration_ms for t in timings) == audio_duration_ms

    def test_proportional_distribution_comma_pause(self):
        service = WordAlignmentService()
        # "casa," has len 5 + comma pause 3 = 8
        # "casa" has len 4 = 4
        timings = service.align_words("casa, casa", 1200)
        assert len(timings) == 2
        assert timings[0].word == "casa,"
        assert timings[1].word == "casa"
        # Word with comma pause should have greater duration than word without
        assert timings[0].duration_ms > timings[1].duration_ms
        assert timings[0].duration_ms + timings[1].duration_ms == 1200
        # 8 / 12 * 1200 = 800, 4 / 12 * 1200 = 400
        assert timings[0].duration_ms == 800
        assert timings[1].duration_ms == 400

    def test_proportional_distribution_sentence_break_pauses(self):
        service = WordAlignmentService()
        # Compare period, exclamation, question, ellipsis, semicolon
        text = "fim. fim! fim? fim; fim"
        timings = service.align_words(text, 2500)
        assert len(timings) == 5

        # len("fim.") = 4 + 6 = 10
        # len("fim!") = 4 + 6 = 10
        # len("fim?") = 4 + 6 = 10
        # len("fim;") = 4 + 3 = 7
        # len("fim") = 3 = 3
        t_period, t_excl, t_quest, t_semi, t_plain = timings

        assert t_period.duration_ms == t_excl.duration_ms == t_quest.duration_ms
        assert t_period.duration_ms > t_semi.duration_ms
        assert t_semi.duration_ms > t_plain.duration_ms
        assert sum(t.duration_ms for t in timings) == 2500

    def test_minimum_weight_per_word(self):
        service = WordAlignmentService()
        # "e" has len 1 -> bumped to min weight 2
        # "sol" has len 3 -> weight 3
        # Total weight = 5 -> "e" gets 40%, "sol" gets 60%
        timings = service.align_words("e sol", 1000)
        assert len(timings) == 2
        assert timings[0].word == "e"
        assert timings[0].duration_ms == 400
        assert timings[1].word == "sol"
        assert timings[1].duration_ms == 600
        assert timings[0].start_ms == 0
        assert timings[1].start_ms == 400

    def test_adjust_last_word_exact_sum(self):
        service = WordAlignmentService()
        # Non-divisible total duration 1001 ms across 3 words of equal weight
        timings = service.align_words("um dois tres", 1001)
        assert len(timings) == 3
        assert sum(t.duration_ms for t in timings) == 1001
        assert timings[-1].start_ms + timings[-1].duration_ms == 1001

    def test_text_with_multiple_consecutive_spaces_and_newlines(self):
        service = WordAlignmentService()
        timings = service.align_words("palavra   com \n múltiplos   espaços.", 1500)
        assert len(timings) == 4
        assert [t.word for t in timings] == ["palavra", "com", "múltiplos", "espaços."]
        assert sum(t.duration_ms for t in timings) == 1500

    def test_short_audio_duration_less_than_words_count_does_not_crash(self):
        service = WordAlignmentService()
        # 10 words with total duration of only 3 ms
        text = "uma frase com muitas palavras para testar duracao muito curta"
        words = text.split()
        assert len(words) == 10

        timings = service.align_words(text, 3)
        assert len(timings) == 10
        for t in timings:
            assert t.start_ms >= 0
            assert t.duration_ms >= 0
            assert t.start_ms + t.duration_ms <= 3

        assert sum(t.duration_ms for t in timings) == 3
        assert timings[-1].start_ms + timings[-1].duration_ms == 3


class TestWhisperWordAlignment:
    @pytest.fixture
    def sample_audio(self, tmp_path: Path) -> Path:
        audio = tmp_path / "sample.wav"
        audio.write_bytes(b"RIFFdummywavbytes")
        return audio

    def test_whisper_success_returns_whisper_timings(self, sample_audio: Path):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/align"
            return httpx.Response(
                200,
                json=[
                    {"word": "Olá,", "start": 0.0, "end": 0.45},
                    {"word": "mundo!", "start": 0.5, "end": 1.2},
                ],
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        service = WordAlignmentService(
            whisper_url="http://whisper-sidecar:8000",
            http_client=client,
        )

        timings = service.align_words("Olá, mundo!", 1200, audio_path=sample_audio)

        assert len(timings) == 2
        assert timings[0] == WordTiming(word="Olá,", start_ms=0, duration_ms=450)
        assert timings[1] == WordTiming(word="mundo!", start_ms=500, duration_ms=700)

    def test_whisper_dict_response_format(self, sample_audio: Path):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "words": [
                        {"word": "teste", "start": 0.1, "end": 0.9},
                    ]
                },
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        service = WordAlignmentService(
            whisper_url="http://whisper-sidecar:8000/",
            http_client=client,
        )

        timings = service.align_words("teste", 1000, audio_path=sample_audio)
        assert len(timings) == 1
        assert timings[0] == WordTiming(word="teste", start_ms=100, duration_ms=800)

    def test_whisper_fallback_on_http_500(self, sample_audio: Path):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="Internal Server Error")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        service = WordAlignmentService(
            whisper_url="http://whisper-sidecar:8000",
            http_client=client,
        )

        timings = service.align_words("fallback teste", 1000, audio_path=sample_audio)
        assert len(timings) == 2
        assert timings[0].word == "fallback"
        assert timings[1].word == "teste"
        assert sum(t.duration_ms for t in timings) == 1000

    def test_whisper_fallback_on_timeout(self, sample_audio: Path):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("Request timed out")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        service = WordAlignmentService(
            whisper_url="http://whisper-sidecar:8000",
            http_client=client,
        )

        timings = service.align_words("palavra um", 1000, audio_path=sample_audio)
        assert len(timings) == 2
        assert sum(t.duration_ms for t in timings) == 1000

    def test_whisper_fallback_on_connection_refused(self, sample_audio: Path):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        service = WordAlignmentService(
            whisper_url="http://whisper-sidecar:8000",
            http_client=client,
        )

        timings = service.align_words("palavra um", 1000, audio_path=sample_audio)
        assert len(timings) == 2
        assert sum(t.duration_ms for t in timings) == 1000

    def test_whisper_fallback_on_invalid_json(self, sample_audio: Path):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="not-valid-json")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        service = WordAlignmentService(
            whisper_url="http://whisper-sidecar:8000",
            http_client=client,
        )

        timings = service.align_words("palavra um", 1000, audio_path=sample_audio)
        assert len(timings) == 2
        assert sum(t.duration_ms for t in timings) == 1000

    def test_whisper_fallback_on_word_count_mismatch(self, sample_audio: Path):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=[
                    {"word": "apenas", "start": 0.0, "end": 0.5},
                ],
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        service = WordAlignmentService(
            whisper_url="http://whisper-sidecar:8000",
            http_client=client,
        )

        # 3 words in text, but Whisper returns 1 -> mismatch fallback to native
        timings = service.align_words("apenas três palavras", 1500, audio_path=sample_audio)
        assert len(timings) == 3
        assert sum(t.duration_ms for t in timings) == 1500

    def test_whisper_fallback_on_empty_whisper_response(self, sample_audio: Path):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[])

        client = httpx.Client(transport=httpx.MockTransport(handler))
        service = WordAlignmentService(
            whisper_url="http://whisper-sidecar:8000",
            http_client=client,
        )

        timings = service.align_words("duas palavras", 1000, audio_path=sample_audio)
        assert len(timings) == 2
        assert sum(t.duration_ms for t in timings) == 1000

    def test_whisper_skipped_when_audio_path_is_none(self):
        called = False

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal called
            called = True
            return httpx.Response(200, json=[])

        client = httpx.Client(transport=httpx.MockTransport(handler))
        service = WordAlignmentService(
            whisper_url="http://whisper-sidecar:8000",
            http_client=client,
        )

        timings = service.align_words("teste nativo", 1000, audio_path=None)
        assert not called
        assert len(timings) == 2

    def test_whisper_skipped_when_audio_path_does_not_exist(self, tmp_path: Path):
        called = False

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal called
            called = True
            return httpx.Response(200, json=[])

        client = httpx.Client(transport=httpx.MockTransport(handler))
        service = WordAlignmentService(
            whisper_url="http://whisper-sidecar:8000",
            http_client=client,
        )

        nonexistent = tmp_path / "does_not_exist.wav"
        timings = service.align_words("teste nativo", 1000, audio_path=nonexistent)
        assert not called
        assert len(timings) == 2

    def test_whisper_timestamps_exceeding_audio_duration_are_clamped(self, sample_audio: Path):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=[
                    {"word": "fim", "start": 0.5, "end": 1.8},
                ],
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        service = WordAlignmentService(
            whisper_url="http://whisper-sidecar:8000",
            http_client=client,
        )

        timings = service.align_words("fim", 1000, audio_path=sample_audio)
        assert len(timings) == 1
        assert timings[0].word == "fim"
        assert timings[0].start_ms == 500
        assert timings[0].duration_ms == 500
        assert timings[0].start_ms + timings[0].duration_ms <= 1000

    def test_whisper_out_of_order_timestamps_fallback_to_native(self, sample_audio: Path):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=[
                    {"word": "primeira", "start": 0.6, "end": 0.9},
                    {"word": "segunda", "start": 0.2, "end": 0.5},
                ],
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        service = WordAlignmentService(
            whisper_url="http://whisper-sidecar:8000",
            http_client=client,
        )

        # Non-monotonic timings: second word starts before first ends -> falls back to native
        timings = service.align_words("primeira segunda", 1000, audio_path=sample_audio)
        assert len(timings) == 2
        assert timings[0].start_ms == 0
        assert timings[1].start_ms == timings[0].duration_ms
        assert sum(t.duration_ms for t in timings) == 1000

    def test_whisper_preserves_original_script_punctuation(self, sample_audio: Path):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=[
                    {"word": "olá", "start": 0.0, "end": 0.4},
                    {"word": "mundo", "start": 0.4, "end": 1.0},
                ],
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        service = WordAlignmentService(
            whisper_url="http://whisper-sidecar:8000",
            http_client=client,
        )

        # Script has punctuation "Olá, mundo!" while Whisper returned plain lowercase
        timings = service.align_words("Olá, mundo!", 1000, audio_path=sample_audio)
        assert len(timings) == 2
        assert timings[0].word == "Olá,"
        assert timings[1].word == "mundo!"
        assert timings[0].start_ms == 0
        assert timings[0].duration_ms == 400
        assert timings[1].start_ms == 400
        assert timings[1].duration_ms == 600

    def test_whisper_textual_divergence_fallback_to_native(self, sample_audio: Path):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=[
                    {"word": "inscreva-se", "start": 0.0, "end": 0.5},
                    {"word": "canal", "start": 0.5, "end": 1.0},
                ],
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        service = WordAlignmentService(
            whisper_url="http://whisper-sidecar:8000",
            http_client=client,
        )

        # Words completely diverge from "Olá mundo" -> fallback to native
        timings = service.align_words("Olá mundo", 1000, audio_path=sample_audio)
        assert len(timings) == 2
        assert timings[0].word == "Olá"
        assert timings[1].word == "mundo"
        assert sum(t.duration_ms for t in timings) == 1000

    def test_whisper_accepts_audio_path_as_string(self, sample_audio: Path):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=[
                    {"word": "teste", "start": 0.0, "end": 1.0},
                ],
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        service = WordAlignmentService(
            whisper_url="http://whisper-sidecar:8000",
            http_client=client,
        )

        timings = service.align_words("teste", 1000, audio_path=str(sample_audio))
        assert len(timings) == 1
        assert timings[0].word == "teste"
        assert timings[0].duration_ms == 1000

    def test_whisper_skipped_when_url_is_none(self, sample_audio: Path):
        called = False

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal called
            called = True
            return httpx.Response(200, json=[])

        client = httpx.Client(transport=httpx.MockTransport(handler))
        service = WordAlignmentService(
            whisper_url=None,
            http_client=client,
        )

        timings = service.align_words("teste nativo", 1000, audio_path=sample_audio)
        assert not called
        assert len(timings) == 2
