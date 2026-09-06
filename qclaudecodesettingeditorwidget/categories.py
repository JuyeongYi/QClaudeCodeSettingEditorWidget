"""최상위 설정 키의 카테고리 분류.

CATEGORY_TITLES 의 영어 제목이 번역 소스(tr) 다. 여기 없는 키(스키마가 갱신되어 새로 생긴 키)는
자동으로 OTHER_ID 로 들어간다. env 는 별도 페이지(EnvEditor)에서 다루므로 ENV_KEY 로 분리한다.
"""
from __future__ import annotations

from enum import IntFlag, auto

ENV_KEY = "env"
ENV_ID = "env"
OTHER_ID = "other"
JSON_ID = "json"


class Category(IntFlag):
    """좌측 카테고리 선택용 비트 플래그. 생성 시 `categories=Category.MODEL | Category.HOOKS` 처럼 지정한다."""

    NONE = 0
    AUTH = auto()
    MODEL = auto()
    PERMISSIONS = auto()
    HOOKS = auto()
    MCP = auto()
    PLUGINS = auto()
    SANDBOX = auto()
    CONTEXT = auto()
    GIT = auto()
    UI = auto()
    NOTIFICATIONS = auto()
    AGENTS = auto()
    IDE = auto()
    ADMIN = auto()
    OTHER = auto()   # 스키마에 새로 생겨 분류되지 않은 키
    ENV = auto()     # 환경 변수 페이지
    JSON = auto()    # JSON 페이지
    SETTINGS = (AUTH | MODEL | PERMISSIONS | HOOKS | MCP | PLUGINS | SANDBOX | CONTEXT | GIT | UI
                | NOTIFICATIONS | AGENTS | IDE | ADMIN | OTHER)
    ALL = SETTINGS | ENV | JSON

    @property
    def id(self) -> str:
        return self.name.lower() if self.name else ""

    @classmethod
    def from_id(cls, category_id: str) -> "Category":
        return cls[category_id.upper()]

    @classmethod
    def parse(cls, text: str) -> "Category":
        """"model|hooks,ENV" 같은 문자열을 플래그로. 알 수 없는 이름은 KeyError."""
        out = cls.NONE
        for part in text.replace(",", "|").split("|"):
            part = part.strip()
            if part:
                out |= cls[part.upper()]
        return out


CATEGORY_TITLES: dict[str, str] = {
    "auth": "Auth & API",
    "model": "Model",
    "permissions": "Permissions",
    "hooks": "Hooks",
    "mcp": "MCP",
    "plugins": "Plugins & marketplaces",
    "sandbox": "Sandbox",
    "context": "Skills, memory & context",
    "git": "Git & worktrees",
    "ui": "UI & display",
    "notifications": "Notifications",
    "agents": "Agents, workflows & artifacts",
    "ide": "IDE, shell & browser",
    "admin": "Updates, versions & managed",
    OTHER_ID: "Other",
    ENV_ID: "Environment variables (env)",
    JSON_ID: "JSON",
}

CATEGORIES: list[tuple[str, list[str]]] = [
    ("auth", [
        "apiKeyHelper", "awsCredentialExport", "awsAuthRefresh", "gcpAuthRefresh",
        "forceLoginMethod", "forceLoginOrgUUID", "forceLoginGatewayUrl",
        "otelHeadersHelper", "policyHelper",
    ]),
    ("model", [
        "model", "availableModels", "enforceAvailableModels", "modelOverrides", "fallbackModel",
        "effortLevel", "fastMode", "fastModePerSessionOptIn", "alwaysThinkingEnabled",
        "advisorModel", "teammateDefaultModel", "autoCompactEnabled",
    ]),
    ("permissions", [
        "permissions", "autoMode", "useAutoModeDuringPlan", "disableAutoMode",
        "skipDangerousModePermissionPrompt", "permissionExplainerEnabled",
        "allowManagedPermissionRulesOnly",
    ]),
    ("hooks", [
        "hooks", "disableAllHooks", "allowedHttpHookUrls", "httpHookAllowedEnvVars",
        "allowManagedHooksOnly",
    ]),
    ("mcp", [
        "enableAllProjectMcpServers", "enabledMcpjsonServers", "disabledMcpjsonServers",
        "allowedMcpServers", "deniedMcpServers", "allowManagedMcpServersOnly", "managedMcpServers",
        "allowAllClaudeAiMcps", "disableClaudeAiConnectors",
    ]),
    ("plugins", [
        "enabledPlugins", "pluginConfigs", "extraKnownMarketplaces", "strictKnownMarketplaces",
        "blockedMarketplaces", "skippedMarketplaces", "skippedPlugins", "pluginTrustMessage",
        "pluginSuggestionMarketplaces", "strictPluginOnlyCustomization",
        "channelsEnabled", "allowedChannelPlugins",
    ]),
    ("sandbox", ["sandbox"]),
    ("context", [
        "claudeMd", "claudeMdExcludes", "includeGitInstructions", "autoMemoryEnabled", "autoMemoryDirectory",
        "skillOverrides", "disableBundledSkills", "disableSkillShellExecution",
        "skillListingMaxDescChars", "skillListingBudgetFraction", "plansDirectory", "respectGitignore",
        "agent", "outputStyle", "language", "fileCheckpointingEnabled", "cleanupPeriodDays",
    ]),
    ("git", ["attribution", "includeCoAuthoredBy", "prUrlTemplate", "worktree"]),
    ("ui", [
        "theme", "tui", "viewMode", "editorMode", "vimInsertModeRemaps", "statusLine", "subagentStatusLine",
        "fileSuggestion", "spinnerVerbs", "spinnerTipsEnabled", "spinnerTipsOverride",
        "terminalProgressBarEnabled", "showTurnDuration", "prefersReducedMotion", "showThinkingSummaries",
        "showClearContextOnPlanAccept", "syntaxHighlightingDisabled", "verbose", "diffTool",
        "wheelScrollAccelerationEnabled", "autoScrollEnabled", "emojiCompletionEnabled", "footerLinksRegexes",
        "axScreenReader", "disableAgentView", "externalEditorContext", "respondToBashCommands",
        "askUserQuestionTimeout", "voice", "voiceEnabled",
    ]),
    ("notifications", [
        "preferredNotifChannel", "agentPushNotifEnabled", "inputNeededNotifEnabled", "awaySummaryEnabled",
        "feedbackSurveyRate", "companyAnnouncements",
    ]),
    ("agents", [
        "teammateMode", "disableWorkflows", "workflowKeywordTriggerEnabled", "workflowSizeGuideline",
        "remoteControlAtStartup", "disableRemoteControl", "enableArtifact", "disableArtifact",
    ]),
    ("ide", [
        "autoConnectIde", "autoInstallIdeExtension", "defaultShell", "processWrapper",
        "wslInheritsWindowsSettings", "skipWebFetchPreflight", "browserExternalPageTools",
        "disableBrowserExternalNavigation", "disableMobileSimulatorTools",
    ]),
    ("admin", [
        "$schema", "autoUpdatesChannel", "minimumVersion", "requiredMinimumVersion", "requiredMaximumVersion",
        "parentSettingsBehavior", "forceRemoteSettingsRefresh", "disableDeepLinkRegistration",
        "disableSideloadFlags", "requireCoworkFullVmSandbox", "sshConfigs", "sshHostAllowlist",
    ]),
]


def categorize(keys: list[str], mask: Category = Category.ALL) -> list[tuple[str, list[str]]]:
    """스키마의 최상위 키 목록을 (카테고리 id, 키 목록) 으로 배분. env 제외, 미분류는 OTHER_ID.

    mask 에 없는 카테고리는 결과에서 빠진다.
    """
    known = {k for _, ks in CATEGORIES for k in ks}
    keyset = set(keys)
    result: list[tuple[str, list[str]]] = []
    for cid, ks in CATEGORIES:
        present = [k for k in ks if k in keyset]
        if present and Category.from_id(cid) & mask:
            result.append((cid, present))
    other = [k for k in keys if k not in known and k != ENV_KEY]
    if other and Category.OTHER & mask:
        result.append((OTHER_ID, other))
    return result
