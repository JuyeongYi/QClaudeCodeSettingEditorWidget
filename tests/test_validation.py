"""validation.py 단위 테스트(Qt 위젯 불필요): 스키마 키워드·확장 format·문서 단위 검증."""
import pytest

from qclaudecodesettingeditorwidget import load_schema
from qclaudecodesettingeditorwidget.constants import DISJOINT_NETWORKS, Format, Severity
from qclaudecodesettingeditorwidget.schema import compile_pattern, default_for, json_equal, value_matches
from qclaudecodesettingeditorwidget.validation import (
    Issue,
    SettingValidationWarning,
    _time_zones,
    errors_only,
    is_valid,
    validate,
    validate_settings,
)

SCHEMA = load_schema()


def _paths(issues):
    return [(i.path, i.keyword, i.severity) for i in issues]


@pytest.mark.parametrize("schema, value, keyword", [
    ({"type": "string"}, 3, "type"),
    ({"type": "integer"}, 1.5, "type"),
    ({"type": "integer"}, True, "type"),          # 불리언은 정수가 아니다
    ({"type": "number"}, "1", "type"),
    ({"enum": ["a", "b"]}, "c", "enum"),
    ({"enum": [1]}, True, "enum"),                 # 파이썬 True == 1 이지만 JSON 값으로는 다르다
    ({"const": "x"}, "y", "const"),
    ({"type": "string", "minLength": 1}, "", "minLength"),
    ({"type": "string", "pattern": "^a"}, "ba", "pattern"),
    ({"type": "integer", "minimum": 1000}, 100, "minimum"),
    ({"type": "integer", "exclusiveMinimum": 0}, 0, "exclusiveMinimum"),
    ({"type": "number", "maximum": 1}, 1.5, "maximum"),
    ({"type": "array", "maxItems": 1}, [1, 2], "maxItems"),
    ({"type": "array", "uniqueItems": True}, ["a", "a"], "uniqueItems"),
    ({"type": "object", "required": ["a"]}, {}, "required"),
    ({"type": "object", "additionalProperties": False}, {"x": 1}, "additionalProperties"),
    ({"type": "object", "propertyNames": {"pattern": "^[A-Z]+$"}}, {"bad": 1}, "propertyNames"),
])
def test_keywords_report_errors(schema, value, keyword):
    issues = validate(schema, value, schema)
    assert [i.keyword for i in issues] == [keyword] and issues[0].severity is Severity.ERROR


def test_valid_values_have_no_issues():
    assert validate({"type": "integer", "minimum": 1}, 5.0, {}) == []  # 5.0 은 정수로 본다
    assert validate({"type": "number"}, 1, {}) == []
    assert is_valid({"anyOf": [{"type": "string"}, {"type": "boolean"}]}, True, {})


def test_anyof_reports_the_intended_variant():
    hooks = {"Stop": [{"hooks": [{"type": "http", "url": "not a url"}]}]}
    issues = validate_settings({"hooks": hooks}, SCHEMA)
    assert _paths(issues) == [("hooks.Stop[0].hooks[0].url", "format", Severity.ERROR)]
    missing = validate_settings({"hooks": {"Stop": [{"hooks": [{"type": "http"}]}]}}, SCHEMA)
    assert [(i.path, i.message) for i in missing] == [("hooks.Stop[0].hooks[0]", 'Missing required key "url"')]
    theme = validate_settings({"theme": "custom:"}, SCHEMA)
    assert theme[0].keyword == "anyOf" and "^custom:.+" in theme[0].message
    assert validate_settings({"theme": "custom:solarized"}, SCHEMA) == []


@pytest.mark.parametrize("fmt, good, bad", [
    (Format.URI, ["https://example.com/x", "urn:isbn:1"], ["example.com", "https://", "http:// x"]),
    (Format.URI_PATTERN, ["https://*.example.com/*"], ["*.example.com"]),
    (Format.SEMVER, ["2.1.100", "1.0.0-beta.1"], ["2.1", "v2.1.0", "latest"]),
    (Format.REGEX, [r"(?<proj>[A-Z]+)-(?<num>\d+)", "^a$"], ["(", "a{2,1}"]),
    (Format.PUBLIC_IPV4_CIDR, ["8.8.8.0/24", "1.0.0.0/8"],
     ["203.0.113.0/24", "10.0.0.0/8", "100.64.0.0/10", "8.8.8.8", "8.8.8.1/24", "8.0.0.0/7", "172.0.0.0/8"]),
])
def test_formats(fmt, good, bad):
    schema = {"type": "string", "format": str(fmt)}
    for v in good:
        assert validate(schema, v, schema) == [], v
    for v in bad:
        assert [i.keyword for i in validate(schema, v, schema)] == ["format"], v


def test_soft_formats_are_warnings():
    regex = validate({"type": "string", "format": str(Format.REGEX)}, "(", {})
    assert regex[0].severity is Severity.WARNING
    if not _time_zones():
        pytest.skip("tzdata 가 없어 시간대를 확인할 수 없는 환경")
    tz = {"type": "string", "format": str(Format.TIME_ZONE)}
    assert validate(tz, "Europe/Dublin", tz) == []
    assert validate(tz, "Mars/Olympus", tz)[0].severity is Severity.WARNING


def test_disjoint_networks_and_bundled_gateway_rules():
    schema = {"type": "array", DISJOINT_NETWORKS: True}
    assert [i.path for i in validate(schema, ["8.8.0.0/16", "8.8.8.0/24"], schema, "g")] == ["g[1]"]
    nets = ["8.8.8.0/24", "1.1.1.0/24", "9.9.9.0/24", "4.4.4.0/24", "5.5.5.0/24"]
    assert [i.keyword for i in validate_settings({"gatewayInternalNetworks": nets}, SCHEMA)] == ["maxItems"]


def test_schema_patches_reach_bundled_schema():
    """resource_overrides.json 의 schemaPatches·문서 범위 병합이 번들 스키마에 들어 있다."""
    bad = {"policyHelper": {"path": "/x", "timeoutMs": 100},
           "sshConfigs": [{"id": "a", "name": "A", "sshHost": "h", "sshPort": 70000}],
           "minimumVersion": "2.1", "forceLoginGatewayUrl": "gateway.example.com",
           "allowedMcpServers": [{"serverUrl": "*.example.com"}],
           "footerLinksRegexes": [{"type": "regex", "pattern": "(?<id>[A-Z]+-\\d+)", "url": "https://x/{id}"}]}
    found = {(i.path, i.keyword) for i in validate_settings(bad, SCHEMA)}
    assert found == {("policyHelper.timeoutMs", "minimum"), ("sshConfigs[0].sshPort", "maximum"),
                     ("minimumVersion", "format"), ("forceLoginGatewayUrl", "format"),
                     ("allowedMcpServers[0].serverUrl", "format")}  # JS 이름 그룹 정규식은 통과


def test_document_level_rules():
    issues = validate_settings({"futureKey": 1, "env": {"CLAUDE_CODE_DISABLE_AUTO_MEMORY": "true",
                                                         "N": 5, "bad-name": "x"}}, SCHEMA)
    by_path = {i.path: i for i in issues}
    assert by_path["futureKey"].severity is Severity.WARNING                       # 스키마 밖 키
    assert by_path["env.CLAUDE_CODE_DISABLE_AUTO_MEMORY"].severity is Severity.WARNING  # env enum 은 느슨하게
    assert by_path["env.N"].severity is Severity.ERROR and by_path["env.bad-name"].keyword == "propertyNames"
    assert Issue("env.X", "m").key == "env" and Issue("a[0].b", "m").key == "a"
    assert errors_only(issues) == [by_path["env.N"], by_path["env.bad-name"]]
    w = SettingValidationWarning(issues)
    assert w.issues == issues and "problem" in str(w)


def test_shared_helpers():
    rx = compile_pattern(r"(?<a>x)\k<a>")                              # JS 이름 그룹·역참조를 파이썬 문법으로
    assert rx is not None and rx.search("xx")
    assert compile_pattern("(") is None
    assert json_equal(1, 1.0) and not json_equal(True, 1) and json_equal({"a": [1]}, {"a": [1.0]})
    assert not value_matches({"enum": [1]}, True, {})
    assert default_for({"type": "integer", "minimum": 1000}, {}) == 1000
    assert default_for({"type": "integer", "exclusiveMinimum": 0}, {}) == 1
    assert default_for({"type": "object", "required": ["t"], "properties": {"t": {"const": "c"}}}, {}) == {"t": "c"}
