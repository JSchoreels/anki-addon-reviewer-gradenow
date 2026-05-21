import logging
import re
import subprocess


logger = logging.getLogger(__name__)

SKIPPED_POS = {"記号", "補助記号", "空白"}


def is_cjk_char(char):
    code = ord(char)
    return (
        0x4E00 <= code <= 0x9FFF
        or 0x3400 <= code <= 0x4DBF
        or 0x20000 <= code <= 0x2A6DF
        or 0x3040 <= code <= 0x309F
        or 0x30A0 <= code <= 0x30FF
        or 0xAC00 <= code <= 0xD7AF
    )


def contains_cjk(text):
    return any(is_cjk_char(char) for char in text)


def append_unique(values, value):
    if value and value != "*" and value not in values:
        values.append(value)


class MecabAnalyzer:
    def __init__(self, commands=None):
        self._commands = commands or [
            "mecab",
            "/usr/local/bin/mecab",
            "/opt/homebrew/bin/mecab",
        ]
        self.base_cmd = None
        self.encoding = "utf-8"
        self.setup()

    @property
    def available(self):
        return bool(self.base_cmd)

    def setup(self):
        for command in self._commands:
            try:
                result = subprocess.run(
                    [command, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
            except Exception:
                logger.warning(
                    "MeCab availability check failed for %s", command, exc_info=True
                )
                continue

            if result.returncode != 0:
                continue

            self.base_cmd = [command]
            self._load_dictionary_encoding(command)
            logger.info("MeCab subprocess setup successful with command: %s", command)
            return

        logger.info("MeCab command not found; CJK morphology search is disabled")

    def _load_dictionary_encoding(self, command):
        try:
            result = subprocess.run(
                [command, "-D"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return
        except Exception:
            logger.warning("MeCab dictionary encoding lookup failed", exc_info=True)
            return

        if result.returncode != 0:
            return

        charset_match = re.search(r"^charset:\s*(.*)$", result.stdout, re.M)
        if charset_match:
            self.encoding = charset_match.group(1).strip()

    def extract_terms(self, text):
        """Return ordered morphemes, lemmas, and readings for search."""
        if not self.available:
            return []

        terms = []
        try:
            result = subprocess.run(
                self.base_cmd
                + [
                    "--node-format=%m\t%f[6]\t%f[7]\t%f[0]\n",
                    "--eos-format=",
                    "--unk-format=%m\t*\t*\t*\n",
                ],
                input=text.strip(),
                capture_output=True,
                text=True,
                encoding=self.encoding,
                timeout=5,
            )
        except subprocess.TimeoutExpired:
            logger.warning("MeCab term extraction timed out")
            return []
        except Exception:
            logger.warning("MeCab term extraction failed", exc_info=True)
            return []

        if result.returncode != 0:
            logger.warning(
                "MeCab term extraction failed with code %s: %s",
                result.returncode,
                result.stderr,
            )
            return []

        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue

            parts = line.split("\t")
            if len(parts) < 4:
                continue

            surface = parts[0]
            lemma = parts[1]
            reading = parts[2]
            pos = parts[3]
            if pos in SKIPPED_POS:
                continue

            append_unique(terms, surface)
            append_unique(terms, lemma)
            append_unique(terms, reading)

        return terms

    def extract_lemmas_with_positions(self, text):
        """Return ordered surface/lemma terms and their morpheme positions."""
        if not self.available:
            return [], {}

        try:
            result = subprocess.run(
                self.base_cmd,
                input=text.strip(),
                capture_output=True,
                text=True,
                encoding=self.encoding,
                timeout=5,
            )
        except subprocess.TimeoutExpired:
            logger.warning("MeCab position extraction timed out")
            return [], {}
        except Exception:
            logger.warning("MeCab position extraction failed", exc_info=True)
            return [], {}

        if result.returncode != 0:
            logger.warning(
                "MeCab position extraction failed with code %s: %s",
                result.returncode,
                result.stderr,
            )
            return [], {}

        lemmas = []
        positions = {}
        position = 0
        for line in result.stdout.strip().split("\n"):
            if line == "EOS" or not line.strip():
                continue

            parts = line.split("\t")
            if len(parts) < 2:
                continue

            surface = parts[0]
            features = parts[1].split(",")
            lemma = features[6] if len(features) > 6 and features[6] != "*" else surface

            append_unique(lemmas, surface)
            append_unique(lemmas, lemma)

            for value in (surface, lemma):
                if value and value not in positions:
                    positions[value] = position
                lower_value = value.lower()
                if lower_value and lower_value not in positions:
                    positions[lower_value] = position

            position += 1

        return lemmas, positions


mecab_analyzer = MecabAnalyzer()
