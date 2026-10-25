import unittest

from breakpoint.llm import extract_json


class ExtractJson(unittest.TestCase):
    def test_a_regex_quoted_inside_a_string_no_longer_makes_the_whole_reply_unreadable(self):
        reply = r'[{"title": "ReDoS", "description": "the pattern /^(a+)+\.\d$/ backtracks", "code_refs": []}, {"title": "Second"}]'
        got = extract_json(reply)
        self.assertEqual([g["title"] for g in got], ["ReDoS", "Second"])
        self.assertEqual(got[0]["description"], r"the pattern /^(a+)+\.\d$/ backtracks")

    def test_a_windows_path_survives(self):
        got = extract_json(r'{"file": "C:\Users\me\app.js", "line": 3}')
        self.assertEqual(got["file"], r"C:\Users\me\app.js")

    def test_a_raw_line_break_or_tab_inside_a_string_is_accepted(self):
        got = extract_json('[{"title": "a", "description": "first line\nsecond\tline"}, {"title": "b"}]')
        self.assertEqual(got[0]["description"], "first line\nsecond\tline")

    def test_valid_escapes_are_left_alone(self):
        got = extract_json(r'{"a": "line\nbreak \"quoted\" tab\t slash\/ unicode \u00e9 backslash \\ done", "b": "x\\d"}')
        self.assertEqual(got["a"], 'line\nbreak "quoted" tab\t slash/ unicode \u00e9 backslash \\ done')
        self.assertEqual(got["b"], "x\\d")                           # an escaped backslash followed by d is not a bad escape

    def test_the_older_repairs_still_work(self):
        self.assertEqual(extract_json('```json\n[{"a": True,}, {"b": None,},]\n```'), [{"a": True}, {"b": None}])


if __name__ == "__main__":
    unittest.main()
