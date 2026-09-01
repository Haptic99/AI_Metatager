import pytest
from ai_metatagger.core.subtitle_tools import is_same_lang_family, map_lang, is_hearing_impaired, get_clean_title

def test_is_same_lang_family():
    assert is_same_lang_family("deu", "ger") is True
    assert is_same_lang_family("zh-Hans", "chi") is True
    assert is_same_lang_family("pt-BR", "por") is True
    assert is_same_lang_family("eng", "ger") is False
    assert is_same_lang_family("en", "eng") is True
    assert is_same_lang_family(None, "eng") is False

def test_map_lang():
    assert map_lang("deu") == "ger"
    assert map_lang("de") == "ger"
    assert map_lang("eng") == "eng"
    assert map_lang("fra") == "fre"
    assert map_lang("chi", "simplified") == "zh-Hans"
    assert map_lang("zh-tw") == "zh-Hant"

def test_is_hearing_impaired():
    # A text with many brackets should be detected as SDH
    sdh_text = "[Knall]\nHallo!\n(Musik spielt)\nWie geht es dir?\n[Husten]"
    # Need at least 8 markers for small texts
    sdh_text_many = "\n".join(["[Sound]"] * 10)
    assert is_hearing_impaired(sdh_text_many, line_count=10) is True
    
    # Normal text without brackets
    normal_text = "Hallo!\nWie geht es dir?\nMir geht es gut."
    assert is_hearing_impaired(normal_text, line_count=3) is False
    
    # Text with one bracket but mostly normal text (should not trigger)
    mostly_normal = "(Lacht)\n" + "\n".join(["Normal text"] * 50)
    assert is_hearing_impaired(mostly_normal, line_count=51) is False

from ai_metatagger.core.subtitle_tools import is_same_lang_family, map_lang, is_hearing_impaired, get_clean_title, is_duplicate_text

def test_get_clean_title():
    assert get_clean_title('zh-Hans', 'srt', False) == "Vereinfachtes Chinesisch"
    assert get_clean_title('zh-Hant', 'srt', False) == "Traditionelles Chinesisch"
    assert get_clean_title('ger', 'srt', True) == ""

def test_is_duplicate_text():
    text1 = "Hallo, das ist ein Test für Duplikate."
    text2 = "Hallo, das ist ein Test für Duplikate."
    text3 = "Hallo, das ist ein Test für Duplikate!" # slightly different
    text4 = "Ganz anderer Text"
    
    assert is_duplicate_text(text1, text2) is True
    assert is_duplicate_text(text1, text3) is True # difflib ratio should be > 0.90
    assert is_duplicate_text(text1, text4) is False
    assert is_duplicate_text("", text4) is False
