from nerddiary.core.report.report import Report


class TestReport:
    def test_correct_json_parse(self):
        r = Report(name="Test")
        assert r
