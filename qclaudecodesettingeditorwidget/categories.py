"""최상위 설정 키의 카테고리 분류.

키는 문자열 대신 keys.SettingKey 멤버로 적는다(SettingKey 는 str 겸용이라 스키마 dict 조회에 그대로 쓰인다).
CATEGORY_TITLES 의 영어 제목이 번역 소스(tr) 다. 여기 없는 키(스키마가 갱신되어 새로 생긴 키)는
자동으로 OTHER_ID 로 들어간다. env 는 별도 페이지(EnvEditor)에서 다루므로 ENV_KEY 로 분리한다.
"""
from __future__ import annotations

from enum import IntFlag, auto

from .constants import ENV_ID, ENV_KEY, JSON_ID, OTHER_ID
from .keys import SettingKey


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
    OTHER = auto()   # 스키마·문서 갱신으로 새로 생겨 분류되지 않은 키
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

CATEGORIES: list[tuple[str, list[SettingKey]]] = [
    ("auth", [
        SettingKey.apiKeyHelper, SettingKey.awsCredentialExport, SettingKey.awsAuthRefresh, SettingKey.gcpAuthRefresh,
        SettingKey.forceLoginMethod, SettingKey.forceLoginOrgUUID, SettingKey.forceLoginGatewayUrl,
        SettingKey.otelHeadersHelper, SettingKey.policyHelper, SettingKey.allowedProviders, SettingKey.gatewayInternalNetworks,
    ]),
    ("model", [
        SettingKey.model, SettingKey.availableModels, SettingKey.enforceAvailableModels, SettingKey.modelOverrides, SettingKey.fallbackModel,
        SettingKey.effortLevel, SettingKey.fastMode, SettingKey.fastModePerSessionOptIn, SettingKey.alwaysThinkingEnabled,
        SettingKey.advisorModel, SettingKey.teammateDefaultModel, SettingKey.autoCompactEnabled,
        SettingKey.availableModelsMatch, SettingKey.deniedModels, SettingKey.maxEffortLevel, SettingKey.modelPicker,
        SettingKey.modelPricing, SettingKey.modelSettings, SettingKey.promptCacheTtl, SettingKey.subagentPromptCacheTtl,
        SettingKey.switchModelsOnFlag, SettingKey.ultracode,
    ]),
    ("permissions", [
        SettingKey.permissions, SettingKey.autoMode, SettingKey.useAutoModeDuringPlan, SettingKey.disableAutoMode,
        SettingKey.skipDangerousModePermissionPrompt, SettingKey.skipAutoPermissionPrompt, SettingKey.permissionExplainerEnabled,
        SettingKey.allowManagedPermissionRulesOnly,
    ]),
    ("hooks", [
        SettingKey.hooks, SettingKey.disableAllHooks, SettingKey.allowedHttpHookUrls, SettingKey.httpHookAllowedEnvVars,
        SettingKey.allowManagedHooksOnly,
    ]),
    ("mcp", [
        SettingKey.enableAllProjectMcpServers, SettingKey.enabledMcpjsonServers, SettingKey.disabledMcpjsonServers,
        SettingKey.allowedMcpServers, SettingKey.deniedMcpServers, SettingKey.allowManagedMcpServersOnly, SettingKey.managedMcpServers,
        SettingKey.allowAllClaudeAiMcps, SettingKey.disableClaudeAiConnectors, SettingKey.allowClaudeInChromeWithManagedMcp,
    ]),
    ("plugins", [
        SettingKey.enabledPlugins, SettingKey.pluginConfigs, SettingKey.extraKnownMarketplaces, SettingKey.strictKnownMarketplaces,
        SettingKey.blockedMarketplaces, SettingKey.skippedMarketplaces, SettingKey.skippedPlugins, SettingKey.pluginTrustMessage,
        SettingKey.pluginSuggestionMarketplaces, SettingKey.strictPluginOnlyCustomization,
        SettingKey.channelsEnabled, SettingKey.allowedChannelPlugins, SettingKey.prependPlugins, SettingKey.appendPlugins,
        SettingKey.disableCommandPluginSources, SettingKey.syncClaudeAiPlugins, SettingKey.syncClaudeAiSkills,
    ]),
    ("sandbox", [SettingKey.sandbox]),
    ("context", [
        SettingKey.claudeMd, SettingKey.claudeMdExcludes, SettingKey.includeGitInstructions, SettingKey.autoMemoryEnabled, SettingKey.autoMemoryDirectory,
        SettingKey.skillOverrides, SettingKey.disableBundledSkills, SettingKey.disableSkillShellExecution,
        SettingKey.skillListingMaxDescChars, SettingKey.skillListingBudgetFraction, SettingKey.plansDirectory, SettingKey.respectGitignore,
        SettingKey.agent, SettingKey.outputStyle, SettingKey.language, SettingKey.fileCheckpointingEnabled, SettingKey.cleanupPeriodDays,
        SettingKey.desktopSessionCleanupPeriodDays, SettingKey.autoCompactWindow, SettingKey.idleCompaction,
        SettingKey.bashOutputMaxChars, SettingKey.taskOutputMaxChars,
    ]),
    ("git", [SettingKey.attribution, SettingKey.includeCoAuthoredBy, SettingKey.prUrlTemplate, SettingKey.worktree]),
    ("ui", [
        SettingKey.theme, SettingKey.tui, SettingKey.viewMode, SettingKey.editorMode, SettingKey.vimInsertModeRemaps, SettingKey.statusLine, SettingKey.subagentStatusLine,
        SettingKey.fileSuggestion, SettingKey.spinnerVerbs, SettingKey.spinnerTipsEnabled, SettingKey.spinnerTipsOverride,
        SettingKey.terminalProgressBarEnabled, SettingKey.showTurnDuration, SettingKey.prefersReducedMotion, SettingKey.showThinkingSummaries,
        SettingKey.showClearContextOnPlanAccept, SettingKey.syntaxHighlightingDisabled, SettingKey.verbose, SettingKey.diffTool,
        SettingKey.wheelScrollAccelerationEnabled, SettingKey.autoScrollEnabled, SettingKey.emojiCompletionEnabled, SettingKey.footerLinksRegexes,
        SettingKey.axScreenReader, SettingKey.disableAgentView, SettingKey.externalEditorContext, SettingKey.respondToBashCommands,
        SettingKey.askUserQuestionTimeout, SettingKey.voice, SettingKey.voiceEnabled, SettingKey.maxProseWidth, SettingKey.timeFormat,
        SettingKey.timeZone, SettingKey.spellcheck, SettingKey.keybindingFlavor, SettingKey.promptSuggestionEnabled,
        SettingKey.terminalTitleFromRename, SettingKey.autoContinueAtUsageLimit, SettingKey.bashEditDiffEnabled,
        SettingKey.dialogExpiry,
    ]),
    ("notifications", [
        SettingKey.preferredNotifChannel, SettingKey.agentPushNotifEnabled, SettingKey.inputNeededNotifEnabled, SettingKey.awaySummaryEnabled,
        SettingKey.feedbackSurveyRate, SettingKey.feedbackDrafts, SettingKey.companyAnnouncements,
    ]),
    ("agents", [
        SettingKey.teammateMode, SettingKey.disableWorkflows, SettingKey.workflowKeywordTriggerEnabled, SettingKey.workflowSizeGuideline,
        SettingKey.remoteControlAtStartup, SettingKey.disableRemoteControl, SettingKey.enableArtifact, SettingKey.disableArtifact,
        SettingKey.enableWorkflows, SettingKey.crossSessionInbound, SettingKey.isolatePeerMachines, SettingKey.remote,
    ]),
    ("ide", [
        SettingKey.autoConnectIde, SettingKey.autoInstallIdeExtension, SettingKey.defaultShell, SettingKey.processWrapper,
        SettingKey.wslInheritsWindowsSettings, SettingKey.skipWebFetchPreflight, SettingKey.browserExternalPageTools,
        SettingKey.disableBrowserExternalNavigation, SettingKey.disableMobileSimulatorTools, SettingKey.disableDesktopLocalSessions,
    ]),
    ("admin", [
        SettingKey.schema, SettingKey.autoUpdatesChannel, SettingKey.minimumVersion, SettingKey.requiredMinimumVersion, SettingKey.requiredMaximumVersion,
        SettingKey.parentSettingsBehavior, SettingKey.forceRemoteSettingsRefresh, SettingKey.disableDeepLinkRegistration,
        SettingKey.disableSideloadFlags, SettingKey.requireCoworkFullVmSandbox, SettingKey.sshConfigs, SettingKey.sshHostAllowlist,
        SettingKey.sshHostCommands, SettingKey.managedSourcesBehavior,
    ]),
]


def categorize(keys: list[str], mask: Category = Category.ALL) -> list[tuple[str, list[SettingKey]]]:
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
