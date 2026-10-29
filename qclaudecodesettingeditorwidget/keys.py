"""설정 키 enum + 키별 메타데이터 — Claude Code v2.1.312 기준.

tools/refresh_resources.py 가 공식 문서(settings-reference)·schemastore 스키마·CHANGELOG 에서 자동 생성한다.
직접 수정하지 말 것: 보정은 tools/resource_overrides.json 에 적고 다시 생성한다.

멤버 이름이 곧 키다: SettingKey.model == "model". 식별자가 될 수 없는 키만 이름이 다르다
(SettingKey.schema.value == "$schema"). 각 멤버의 .info 가 SettingInfo(스코프·타입·기본값·값 후보·버전).
중첩 경로(sandbox.bwrapPath 등)의 메타데이터는 NESTED_SETTINGS, 통합 조회는 setting_info(path).
스코프·타입·주제는 constants 의 enum, 버전은 Version 으로 적고 문자열은 키와 JSON 값(기본값·값 후보)에만 쓴다.
"""
from __future__ import annotations

from .constants import JsonType, Scope, Topic
from .env_keys import EnvVar
from .spec import KeyEnum, SettingInfo, Version


class SettingKey(KeyEnum):
    """settings.json 최상위 키."""

    @property
    def info(self) -> SettingInfo:
        assert self._info is not None
        return self._info

    schema = SettingInfo("$schema", type=JsonType.STRING, in_docs=False)
    apiKeyHelper = SettingInfo("apiKeyHelper", type=JsonType.STRING, topic=Topic.AUTH)
    autoMemoryEnabled = SettingInfo("autoMemoryEnabled", type=JsonType.BOOLEAN, default=True, topic=Topic.MEMORY)
    autoUpdatesChannel = SettingInfo(
        "autoUpdatesChannel", type=JsonType.STRING, default="latest", values=("stable", "latest"), topic=Topic.UPDATES)
    awsCredentialExport = SettingInfo("awsCredentialExport", type=JsonType.STRING, topic=Topic.AUTH)
    awsAuthRefresh = SettingInfo("awsAuthRefresh", type=JsonType.STRING, topic=Topic.AUTH)
    claudeMdExcludes = SettingInfo("claudeMdExcludes", type=JsonType.ARRAY, topic=Topic.MEMORY)
    cleanupPeriodDays = SettingInfo("cleanupPeriodDays", type=JsonType.INTEGER, default=30, topic=Topic.PRIVACY)
    env = SettingInfo("env", type=JsonType.OBJECT, default={}, topic=Topic.MEMORY)
    attribution = SettingInfo("attribution", type=JsonType.OBJECT, since=Version(2, 0, 62), topic=Topic.GIT)
    includeGitInstructions = SettingInfo(
        "includeGitInstructions", type=JsonType.BOOLEAN, default=True, since=Version(2, 1, 69), topic=Topic.GIT)
    includeCoAuthoredBy = SettingInfo(
        "includeCoAuthoredBy", type=JsonType.BOOLEAN, default=True, deprecated=True, deprecated_since=Version(2, 0, 62),
        replaced_by=attribution, topic=Topic.GIT)
    plansDirectory = SettingInfo(
        "plansDirectory", type=JsonType.STRING, default="~/.claude/plans", since=Version(2, 1, 9), topic=Topic.MEMORY)
    respectGitignore = SettingInfo("respectGitignore", type=JsonType.BOOLEAN, default=True, topic=Topic.INTERFACE)
    permissions = SettingInfo("permissions", type=JsonType.OBJECT, topic=Topic.PERMISSIONS)
    language = SettingInfo("language", type=JsonType.STRING, since=Version(2, 1, 0), topic=Topic.MODEL)
    model = SettingInfo("model", type=JsonType.STRING, topic=Topic.MODEL)
    availableModels = SettingInfo("availableModels", type=JsonType.ARRAY, topic=Topic.MODEL)
    modelOverrides = SettingInfo("modelOverrides", type=JsonType.OBJECT, since=Version(2, 1, 73), topic=Topic.MODEL)
    effortLevel = SettingInfo(
        "effortLevel", type=JsonType.STRING, values=("low", "medium", "high", "xhigh"), topic=Topic.MODEL)
    fastMode = SettingInfo("fastMode", type=JsonType.BOOLEAN, default=False, topic=Topic.MODEL)
    fastModePerSessionOptIn = SettingInfo(
        "fastModePerSessionOptIn", type=JsonType.BOOLEAN, default=False, topic=Topic.MODEL)
    feedbackSurveyRate = SettingInfo("feedbackSurveyRate", type=JsonType.NUMBER, topic=Topic.PRIVACY)
    enableAllProjectMcpServers = SettingInfo("enableAllProjectMcpServers", type=JsonType.BOOLEAN, topic=Topic.MCP)
    enabledMcpjsonServers = SettingInfo("enabledMcpjsonServers", type=JsonType.ARRAY, topic=Topic.MCP)
    disabledMcpjsonServers = SettingInfo("disabledMcpjsonServers", type=JsonType.ARRAY, topic=Topic.MCP)
    allowedMcpServers = SettingInfo("allowedMcpServers", type=JsonType.ARRAY, topic=Topic.MCP)
    deniedMcpServers = SettingInfo("deniedMcpServers", type=JsonType.ARRAY, topic=Topic.MCP)
    httpHookAllowedEnvVars = SettingInfo("httpHookAllowedEnvVars", type=JsonType.ARRAY, topic=Topic.HOOKS)
    hooks = SettingInfo("hooks", type=JsonType.OBJECT, topic=Topic.HOOKS)
    disableAllHooks = SettingInfo("disableAllHooks", type=JsonType.BOOLEAN, since=Version(1, 0, 68), topic=Topic.HOOKS)
    allowedChannelPlugins = SettingInfo(
        "allowedChannelPlugins", scope=Scope.MANAGED, type=JsonType.ARRAY, since=Version(2, 1, 84), topic=Topic.PLUGINS)
    allowedHttpHookUrls = SettingInfo("allowedHttpHookUrls", type=JsonType.ARRAY, topic=Topic.HOOKS)
    allowManagedHooksOnly = SettingInfo(
        "allowManagedHooksOnly", scope=Scope.MANAGED, type=JsonType.BOOLEAN, topic=Topic.HOOKS)
    allowManagedPermissionRulesOnly = SettingInfo(
        "allowManagedPermissionRulesOnly", scope=Scope.MANAGED, type=JsonType.BOOLEAN, topic=Topic.PERMISSIONS)
    statusLine = SettingInfo("statusLine", type=JsonType.OBJECT, topic=Topic.INTERFACE)
    fileSuggestion = SettingInfo("fileSuggestion", type=JsonType.OBJECT, since=Version(2, 0, 65), topic=Topic.INTERFACE)
    enabledPlugins = SettingInfo("enabledPlugins", type=JsonType.OBJECT, topic=Topic.PLUGINS)
    extraKnownMarketplaces = SettingInfo("extraKnownMarketplaces", type=JsonType.OBJECT, topic=Topic.PLUGINS)
    strictKnownMarketplaces = SettingInfo(
        "strictKnownMarketplaces", scope=Scope.MANAGED, type=JsonType.ARRAY, topic=Topic.PLUGINS)
    skippedMarketplaces = SettingInfo("skippedMarketplaces", type=JsonType.ARRAY, in_docs=False)
    skippedPlugins = SettingInfo("skippedPlugins", type=JsonType.ARRAY, in_docs=False)
    forceLoginMethod = SettingInfo(
        "forceLoginMethod", type=JsonType.STRING, values=("claudeai", "console", "gateway"), topic=Topic.AUTH)
    forceLoginOrgUUID = SettingInfo("forceLoginOrgUUID", type=JsonType.STRING | JsonType.ARRAY, topic=Topic.AUTH)
    otelHeadersHelper = SettingInfo("otelHeadersHelper", type=JsonType.STRING, topic=Topic.AUTH)
    outputStyle = SettingInfo("outputStyle", type=JsonType.STRING, topic=Topic.MODEL)
    skipWebFetchPreflight = SettingInfo("skipWebFetchPreflight", type=JsonType.BOOLEAN, topic=Topic.PRIVACY)
    sandbox = SettingInfo("sandbox", type=JsonType.OBJECT, topic=Topic.SANDBOX)
    spinnerVerbs = SettingInfo("spinnerVerbs", type=JsonType.OBJECT, topic=Topic.INTERFACE)
    spinnerTipsEnabled = SettingInfo(
        "spinnerTipsEnabled", type=JsonType.BOOLEAN, default=True, since=Version(1, 0, 112), topic=Topic.INTERFACE)
    spinnerTipsOverride = SettingInfo(
        "spinnerTipsOverride", type=JsonType.OBJECT, since=Version(2, 1, 45), topic=Topic.INTERFACE)
    terminalProgressBarEnabled = SettingInfo(
        "terminalProgressBarEnabled", type=JsonType.BOOLEAN, default=True, topic=Topic.INTERFACE)
    showTurnDuration = SettingInfo(
        "showTurnDuration", type=JsonType.BOOLEAN, default=True, since=Version(2, 1, 7), topic=Topic.INTERFACE)
    skillOverrides = SettingInfo("skillOverrides", type=JsonType.OBJECT, topic=Topic.PLUGINS)
    prefersReducedMotion = SettingInfo(
        "prefersReducedMotion", type=JsonType.BOOLEAN, default=False, topic=Topic.INTERFACE)
    prUrlTemplate = SettingInfo("prUrlTemplate", type=JsonType.STRING, since=Version(2, 1, 119), topic=Topic.GIT)
    alwaysThinkingEnabled = SettingInfo("alwaysThinkingEnabled", type=JsonType.BOOLEAN, topic=Topic.MODEL)
    companyAnnouncements = SettingInfo(
        "companyAnnouncements", type=JsonType.ARRAY, since=Version(2, 0, 32), topic=Topic.INTERFACE)
    teammateMode = SettingInfo(
        "teammateMode", type=JsonType.STRING, default="in-process", values=("auto", "in-process", "tmux", "iterm2"),
        topic=Topic.AGENTS)
    worktree = SettingInfo("worktree", type=JsonType.OBJECT, topic=Topic.AGENTS)
    parentSettingsBehavior = SettingInfo(
        "parentSettingsBehavior", scope=Scope.MANAGED, type=JsonType.STRING, default="first-wins",
        values=("first-wins", "merge"), topic=Topic.ENTERPRISE)
    pluginTrustMessage = SettingInfo(
        "pluginTrustMessage", scope=Scope.MANAGED, type=JsonType.STRING, since=Version(2, 1, 69), topic=Topic.PLUGINS)
    pluginConfigs = SettingInfo(
        "pluginConfigs", scope=Scope.USER | Scope.MANAGED, type=JsonType.OBJECT, topic=Topic.PLUGINS)
    allowManagedMcpServersOnly = SettingInfo(
        "allowManagedMcpServersOnly", scope=Scope.MANAGED, type=JsonType.BOOLEAN, default=False, topic=Topic.MCP)
    blockedMarketplaces = SettingInfo(
        "blockedMarketplaces", scope=Scope.MANAGED, type=JsonType.ARRAY, topic=Topic.PLUGINS)
    agent = SettingInfo("agent", type=JsonType.STRING, since=Version(2, 0, 59), topic=Topic.AGENTS)
    autoMemoryDirectory = SettingInfo(
        "autoMemoryDirectory", type=JsonType.STRING, since=Version(2, 1, 74), topic=Topic.MEMORY)
    autoMode = SettingInfo("autoMode", scope=Scope.USER | Scope.MANAGED, type=JsonType.OBJECT, topic=Topic.PERMISSIONS)
    channelsEnabled = SettingInfo("channelsEnabled", scope=Scope.MANAGED, type=JsonType.BOOLEAN, topic=Topic.PLUGINS)
    defaultShell = SettingInfo(
        "defaultShell", type=JsonType.STRING, default="bash", values=("bash", "powershell"), topic=Topic.INTERFACE)
    disableDeepLinkRegistration = SettingInfo(
        "disableDeepLinkRegistration", type=JsonType.STRING, values=("disable",), since=Version(2, 1, 83),
        topic=Topic.REMOTE)
    disableSkillShellExecution = SettingInfo(
        "disableSkillShellExecution", type=JsonType.BOOLEAN, since=Version(2, 1, 91), topic=Topic.PLUGINS)
    forceRemoteSettingsRefresh = SettingInfo(
        "forceRemoteSettingsRefresh", scope=Scope.MANAGED, type=JsonType.BOOLEAN, default=False,
        since=Version(2, 1, 92), topic=Topic.ENTERPRISE)
    minimumVersion = SettingInfo("minimumVersion", type=JsonType.STRING, topic=Topic.UPDATES)
    showClearContextOnPlanAccept = SettingInfo(
        "showClearContextOnPlanAccept", type=JsonType.BOOLEAN, default=False, topic=Topic.INTERFACE)
    showThinkingSummaries = SettingInfo(
        "showThinkingSummaries", type=JsonType.BOOLEAN, default=False, topic=Topic.MODEL)
    skipDangerousModePermissionPrompt = SettingInfo(
        "skipDangerousModePermissionPrompt", scope=Scope.USER | Scope.LOCAL | Scope.MANAGED, type=JsonType.BOOLEAN,
        topic=Topic.PERMISSIONS)
    strictPluginOnlyCustomization = SettingInfo(
        "strictPluginOnlyCustomization", scope=Scope.MANAGED, type=JsonType.BOOLEAN | JsonType.ARRAY,
        topic=Topic.PLUGINS)
    tui = SettingInfo("tui", type=JsonType.STRING, values=("fullscreen", "default"), topic=Topic.INTERFACE)
    viewMode = SettingInfo(
        "viewMode", type=JsonType.STRING, values=("default", "verbose", "focus"), topic=Topic.INTERFACE)
    useAutoModeDuringPlan = SettingInfo(
        "useAutoModeDuringPlan", scope=Scope.USER | Scope.LOCAL | Scope.MANAGED, type=JsonType.BOOLEAN, default=True,
        topic=Topic.PERMISSIONS)
    wslInheritsWindowsSettings = SettingInfo(
        "wslInheritsWindowsSettings", scope=Scope.MANAGED, type=JsonType.BOOLEAN, default=False, topic=Topic.ENTERPRISE)
    subagentStatusLine = SettingInfo("subagentStatusLine", type=JsonType.OBJECT, topic=Topic.INTERFACE)
    advisorModel = SettingInfo("advisorModel", type=JsonType.STRING, topic=Topic.MODEL)
    autoCompactEnabled = SettingInfo("autoCompactEnabled", type=JsonType.BOOLEAN, default=True, topic=Topic.MEMORY)
    disableAgentView = SettingInfo("disableAgentView", type=JsonType.BOOLEAN, topic=Topic.AGENTS)
    editorMode = SettingInfo(
        "editorMode", type=JsonType.STRING, default="normal", values=("normal", "vim"), topic=Topic.INTERFACE)
    enforceAvailableModels = SettingInfo(
        "enforceAvailableModels", type=JsonType.BOOLEAN, default=False, since=Version(2, 1, 175), topic=Topic.MODEL)
    fallbackModel = SettingInfo("fallbackModel", type=JsonType.ARRAY, since=Version(2, 1, 166), topic=Topic.MODEL)
    fileCheckpointingEnabled = SettingInfo(
        "fileCheckpointingEnabled", type=JsonType.BOOLEAN, default=True, topic=Topic.MEMORY)
    gcpAuthRefresh = SettingInfo("gcpAuthRefresh", type=JsonType.STRING, topic=Topic.AUTH)
    managedMcpServers = SettingInfo(
        "managedMcpServers", scope=Scope.MANAGED, type=JsonType.ARRAY, since=Version(2, 1, 259), topic=Topic.MCP)
    skillListingMaxDescChars = SettingInfo(
        "skillListingMaxDescChars", type=JsonType.INTEGER, default=1536, topic=Topic.MEMORY)
    preferredNotifChannel = SettingInfo(
        "preferredNotifChannel", type=JsonType.STRING, default="auto",
        values=("auto", "terminal_bell", "iterm2", "iterm2_with_bell", "kitty", "ghostty", "notifications_disabled"),
        topic=Topic.REMOTE)
    pluginSuggestionMarketplaces = SettingInfo(
        "pluginSuggestionMarketplaces", scope=Scope.MANAGED, type=JsonType.ARRAY, since=Version(2, 1, 152),
        topic=Topic.PLUGINS)
    requiredMaximumVersion = SettingInfo(
        "requiredMaximumVersion", scope=Scope.MANAGED, type=JsonType.STRING, since=Version(2, 1, 163),
        topic=Topic.UPDATES)
    requiredMinimumVersion = SettingInfo(
        "requiredMinimumVersion", scope=Scope.MANAGED, type=JsonType.STRING, since=Version(2, 1, 163),
        topic=Topic.UPDATES)
    respondToBashCommands = SettingInfo(
        "respondToBashCommands", type=JsonType.BOOLEAN, default=True, topic=Topic.INTERFACE)
    skillListingBudgetFraction = SettingInfo(
        "skillListingBudgetFraction", type=JsonType.NUMBER, default=0.01, topic=Topic.MEMORY)
    sshConfigs = SettingInfo("sshConfigs", scope=Scope.USER | Scope.MANAGED, type=JsonType.ARRAY, topic=Topic.REMOTE)
    sshHostAllowlist = SettingInfo("sshHostAllowlist", scope=Scope.MANAGED, type=JsonType.ARRAY, topic=Topic.REMOTE)
    theme = SettingInfo(
        "theme", type=JsonType.STRING, default="dark",
        values=("auto", "dark", "light", "dark-daltonized", "light-daltonized", "dark-ansi", "light-ansi"),
        topic=Topic.INTERFACE)
    voice = SettingInfo("voice", type=JsonType.OBJECT, topic=Topic.INTERFACE)
    voiceEnabled = SettingInfo(
        "voiceEnabled", type=JsonType.BOOLEAN, deprecated=True, deprecated_since=Version(2, 1, 92), replaced_by=voice,
        topic=Topic.INTERFACE)
    wheelScrollAccelerationEnabled = SettingInfo(
        "wheelScrollAccelerationEnabled", type=JsonType.BOOLEAN, default=True, since=Version(2, 1, 174),
        topic=Topic.INTERFACE)
    disableBundledSkills = SettingInfo(
        "disableBundledSkills", type=JsonType.BOOLEAN, since=Version(2, 1, 169), topic=Topic.PLUGINS)
    awaySummaryEnabled = SettingInfo("awaySummaryEnabled", type=JsonType.BOOLEAN, default=True, topic=Topic.REMOTE)
    autoScrollEnabled = SettingInfo("autoScrollEnabled", type=JsonType.BOOLEAN, default=True, topic=Topic.INTERFACE)
    allowAllClaudeAiMcps = SettingInfo(
        "allowAllClaudeAiMcps", scope=Scope.MANAGED, type=JsonType.BOOLEAN, default=False, topic=Topic.MCP)
    agentPushNotifEnabled = SettingInfo(
        "agentPushNotifEnabled", type=JsonType.BOOLEAN, default=False, topic=Topic.REMOTE)
    axScreenReader = SettingInfo(
        "axScreenReader", scope=Scope.USER | Scope.MANAGED, type=JsonType.BOOLEAN, topic=Topic.INTERFACE)
    claudeMd = SettingInfo("claudeMd", scope=Scope.MANAGED, type=JsonType.STRING, topic=Topic.MEMORY)
    disableAutoMode = SettingInfo("disableAutoMode", type=JsonType.STRING, values=("disable",), topic=Topic.PERMISSIONS)
    disableClaudeAiConnectors = SettingInfo(
        "disableClaudeAiConnectors", type=JsonType.BOOLEAN, default=False, topic=Topic.MCP)
    disableRemoteControl = SettingInfo("disableRemoteControl", type=JsonType.BOOLEAN, default=False, topic=Topic.REMOTE)
    disableWorkflows = SettingInfo("disableWorkflows", type=JsonType.BOOLEAN, default=False, topic=Topic.HOOKS)
    footerLinksRegexes = SettingInfo(
        "footerLinksRegexes", scope=Scope.USER | Scope.MANAGED, type=JsonType.ARRAY, since=Version(2, 1, 176),
        topic=Topic.INTERFACE)
    inputNeededNotifEnabled = SettingInfo(
        "inputNeededNotifEnabled", type=JsonType.BOOLEAN, default=False, topic=Topic.REMOTE)
    policyHelper = SettingInfo("policyHelper", scope=Scope.MANAGED, type=JsonType.OBJECT, topic=Topic.ENTERPRISE)
    remoteControlAtStartup = SettingInfo("remoteControlAtStartup", type=JsonType.BOOLEAN, topic=Topic.REMOTE)
    syntaxHighlightingDisabled = SettingInfo(
        "syntaxHighlightingDisabled", type=JsonType.BOOLEAN, default=False, topic=Topic.INTERFACE)
    verbose = SettingInfo("verbose", type=JsonType.BOOLEAN, default=False, topic=Topic.INTERFACE)
    workflowKeywordTriggerEnabled = SettingInfo(
        "workflowKeywordTriggerEnabled", type=JsonType.BOOLEAN, default=True, topic=Topic.HOOKS)
    askUserQuestionTimeout = SettingInfo(
        "askUserQuestionTimeout", scope=Scope.USER | Scope.MANAGED, type=JsonType.STRING, default="never",
        values=("60s", "5m", "10m", "never"), topic=Topic.INTERFACE)
    teammateDefaultModel = SettingInfo(
        "teammateDefaultModel", scope=Scope.GLOBAL_CONFIG, type=JsonType.NULL | JsonType.STRING,
        removed=Version(2, 1, 234), topic=Topic.GLOBAL_CONFIG)
    workflowSizeGuideline = SettingInfo(
        "workflowSizeGuideline", type=JsonType.STRING, default="medium",
        values=("unrestricted", "small", "medium", "large"), since=Version(2, 1, 219), topic=Topic.HOOKS)
    enableArtifact = SettingInfo("enableArtifact", type=JsonType.BOOLEAN, topic=Topic.REMOTE)
    disableArtifact = SettingInfo(
        "disableArtifact", type=JsonType.BOOLEAN, deprecated=True, replaced_by=enableArtifact, topic=Topic.REMOTE)
    permissionExplainerEnabled = SettingInfo(
        "permissionExplainerEnabled", scope=Scope.GLOBAL_CONFIG, type=JsonType.BOOLEAN, default=True,
        removed=Version(2, 1, 257), topic=Topic.GLOBAL_CONFIG)
    diffTool = SettingInfo(
        "diffTool", scope=Scope.GLOBAL_CONFIG, type=JsonType.STRING, default="auto", values=("auto", "terminal"),
        topic=Topic.GLOBAL_CONFIG)
    externalEditorContext = SettingInfo(
        "externalEditorContext", scope=Scope.GLOBAL_CONFIG, type=JsonType.BOOLEAN, default=False,
        topic=Topic.GLOBAL_CONFIG)
    autoConnectIde = SettingInfo(
        "autoConnectIde", scope=Scope.GLOBAL_CONFIG, type=JsonType.BOOLEAN, default=False, topic=Topic.GLOBAL_CONFIG)
    autoInstallIdeExtension = SettingInfo(
        "autoInstallIdeExtension", scope=Scope.GLOBAL_CONFIG, type=JsonType.BOOLEAN, default=True,
        topic=Topic.GLOBAL_CONFIG)
    emojiCompletionEnabled = SettingInfo(
        "emojiCompletionEnabled", type=JsonType.BOOLEAN, default=True, topic=Topic.INTERFACE)
    vimInsertModeRemaps = SettingInfo(
        "vimInsertModeRemaps", scope=Scope.USER | Scope.MANAGED, type=JsonType.OBJECT, since=Version(2, 1, 208),
        topic=Topic.INTERFACE)
    processWrapper = SettingInfo(
        "processWrapper", scope=Scope.USER | Scope.MANAGED, type=JsonType.STRING, since=Version(2, 1, 210),
        topic=Topic.AGENTS)
    forceLoginGatewayUrl = SettingInfo(
        "forceLoginGatewayUrl", scope=Scope.USER | Scope.MANAGED, type=JsonType.STRING, topic=Topic.AUTH)
    disableSideloadFlags = SettingInfo(
        "disableSideloadFlags", scope=Scope.MANAGED, type=JsonType.BOOLEAN, default=False, since=Version(2, 1, 193),
        topic=Topic.ENTERPRISE)
    browserExternalPageTools = SettingInfo(
        "browserExternalPageTools", scope=Scope.MANAGED, type=JsonType.STRING, values=("disabled",), topic=Topic.TOOLS)
    disableBrowserExternalNavigation = SettingInfo(
        "disableBrowserExternalNavigation", scope=Scope.MANAGED, type=JsonType.BOOLEAN, topic=Topic.TOOLS)
    disableMobileSimulatorTools = SettingInfo(
        "disableMobileSimulatorTools", scope=Scope.MANAGED, type=JsonType.BOOLEAN, topic=Topic.TOOLS)
    requireCoworkFullVmSandbox = SettingInfo(
        "requireCoworkFullVmSandbox", scope=Scope.MANAGED, type=JsonType.BOOLEAN, in_docs=False)
    allowClaudeInChromeWithManagedMcp = SettingInfo(
        "allowClaudeInChromeWithManagedMcp", scope=Scope.MANAGED, type=JsonType.BOOLEAN, default=False,
        since=Version(2, 1, 282), topic=Topic.MCP, in_schemastore=False)
    allowedProviders = SettingInfo(
        "allowedProviders", scope=Scope.MANAGED, type=JsonType.ARRAY,
        values=("anthropic", "bedrock", "vertex", "foundry", "anthropicAws", "mantle", "customEndpoint", "gateway"),
        since=Version(2, 1, 285), topic=Topic.AUTH, in_schemastore=False)
    appendPlugins = SettingInfo(
        "appendPlugins", scope=Scope.USER | Scope.MANAGED, type=JsonType.ARRAY, topic=Topic.PLUGINS,
        in_schemastore=False)
    autoCompactWindow = SettingInfo(
        "autoCompactWindow", type=JsonType.INTEGER, topic=Topic.MEMORY, in_schemastore=False)
    autoContinueAtUsageLimit = SettingInfo(
        "autoContinueAtUsageLimit", scope=Scope.USER | Scope.MANAGED, type=JsonType.BOOLEAN, default=True,
        since=Version(2, 1, 234), topic=Topic.INTERFACE, in_schemastore=False)
    availableModelsMatch = SettingInfo(
        "availableModelsMatch", scope=Scope.MANAGED, type=JsonType.STRING, default="prefix", values=("prefix", "exact"),
        since=Version(2, 1, 283), topic=Topic.MODEL, in_schemastore=False)
    bashEditDiffEnabled = SettingInfo(
        "bashEditDiffEnabled", scope=Scope.USER | Scope.MANAGED, type=JsonType.BOOLEAN, since=Version(2, 1, 269),
        topic=Topic.INTERFACE, in_schemastore=False)
    bashOutputMaxChars = SettingInfo(
        "bashOutputMaxChars", type=JsonType.INTEGER, since=Version(2, 1, 261), topic=Topic.MEMORY, in_schemastore=False)
    crossSessionInbound = SettingInfo(
        "crossSessionInbound", type=JsonType.STRING, values=("accept", "hold", "refuse"), since=Version(2, 1, 224),
        topic=Topic.AGENTS, in_schemastore=False)
    deniedModels = SettingInfo(
        "deniedModels", scope=Scope.MANAGED, type=JsonType.ARRAY, since=Version(2, 1, 283), topic=Topic.MODEL,
        in_schemastore=False)
    desktopSessionCleanupPeriodDays = SettingInfo(
        "desktopSessionCleanupPeriodDays", scope=Scope.USER | Scope.MANAGED, type=JsonType.INTEGER, default=0,
        since=Version(2, 1, 248), topic=Topic.PRIVACY, in_schemastore=False)
    dialogExpiry = SettingInfo(
        "dialogExpiry", scope=Scope.USER | Scope.MANAGED, type=JsonType.STRING, default="5m",
        values=("60s", "5m", "10m", "never"), since=Version(2, 1, 224), topic=Topic.INTERFACE, in_schemastore=False)
    disableCommandPluginSources = SettingInfo(
        "disableCommandPluginSources", scope=Scope.MANAGED, type=JsonType.BOOLEAN, since=Version(2, 1, 229),
        topic=Topic.PLUGINS, in_schemastore=False)
    disableDesktopLocalSessions = SettingInfo(
        "disableDesktopLocalSessions", scope=Scope.MANAGED, type=JsonType.BOOLEAN, topic=Topic.REMOTE,
        in_schemastore=False)
    enableWorkflows = SettingInfo("enableWorkflows", type=JsonType.BOOLEAN, topic=Topic.HOOKS, in_schemastore=False)
    feedbackDrafts = SettingInfo(
        "feedbackDrafts", scope=Scope.USER | Scope.MANAGED, type=JsonType.STRING, default="notify",
        values=("notify", "quiet", "off"), topic=Topic.PRIVACY, in_schemastore=False)
    gatewayInternalNetworks = SettingInfo(
        "gatewayInternalNetworks", scope=Scope.MANAGED, type=JsonType.ARRAY, since=Version(2, 1, 268), topic=Topic.AUTH,
        in_schemastore=False)
    idleCompaction = SettingInfo(
        "idleCompaction", type=JsonType.BOOLEAN, default=True, topic=Topic.MEMORY, in_schemastore=False)
    isolatePeerMachines = SettingInfo(
        "isolatePeerMachines", type=JsonType.BOOLEAN, topic=Topic.AGENTS, in_schemastore=False)
    keybindingFlavor = SettingInfo(
        "keybindingFlavor", type=JsonType.STRING, values=("classic", "readline"), since=Version(2, 1, 238),
        deprecated=True, deprecated_since=Version(2, 1, 261), topic=Topic.INTERFACE, in_schemastore=False)
    managedSourcesBehavior = SettingInfo(
        "managedSourcesBehavior", scope=Scope.MANAGED, type=JsonType.STRING, default="first-wins",
        values=("first-wins", "merge"), since=Version(2, 1, 242), topic=Topic.ENTERPRISE, in_schemastore=False)
    maxEffortLevel = SettingInfo(
        "maxEffortLevel", type=JsonType.STRING, values=("low", "medium", "high", "xhigh", "max"),
        since=Version(2, 1, 267), topic=Topic.MODEL, in_schemastore=False)
    maxProseWidth = SettingInfo(
        "maxProseWidth", type=JsonType.INTEGER, since=Version(2, 1, 282), topic=Topic.INTERFACE, in_schemastore=False)
    modelPicker = SettingInfo(
        "modelPicker", scope=Scope.USER | Scope.MANAGED, type=JsonType.OBJECT, since=Version(2, 1, 242),
        topic=Topic.MODEL, in_schemastore=False)
    modelPricing = SettingInfo(
        "modelPricing", scope=Scope.MANAGED, type=JsonType.OBJECT, since=Version(2, 1, 242), topic=Topic.MODEL,
        in_schemastore=False)
    modelSettings = SettingInfo(
        "modelSettings", type=JsonType.OBJECT, since=Version(2, 1, 251), topic=Topic.MODEL, in_schemastore=False)
    prependPlugins = SettingInfo(
        "prependPlugins", scope=Scope.USER | Scope.MANAGED, type=JsonType.ARRAY, topic=Topic.PLUGINS,
        in_schemastore=False)
    promptCacheTtl = SettingInfo(
        "promptCacheTtl", type=JsonType.STRING, values=("5m", "1h"), since=Version(2, 1, 242), topic=Topic.MODEL,
        in_schemastore=False)
    promptSuggestionEnabled = SettingInfo(
        "promptSuggestionEnabled", type=JsonType.BOOLEAN, default=True, topic=Topic.INTERFACE, in_schemastore=False)
    remote = SettingInfo("remote", type=JsonType.OBJECT, in_docs=False, in_schemastore=False)
    skipAutoPermissionPrompt = SettingInfo(
        "skipAutoPermissionPrompt", scope=Scope.USER | Scope.MANAGED, type=JsonType.BOOLEAN, topic=Topic.PERMISSIONS,
        in_schemastore=False)
    spellcheck = SettingInfo(
        "spellcheck", scope=Scope.USER | Scope.MANAGED, type=JsonType.OBJECT, since=Version(2, 1, 235),
        topic=Topic.INTERFACE, in_schemastore=False)
    sshHostCommands = SettingInfo(
        "sshHostCommands", scope=Scope.USER | Scope.MANAGED, type=JsonType.ARRAY, topic=Topic.REMOTE,
        in_schemastore=False)
    subagentPromptCacheTtl = SettingInfo(
        "subagentPromptCacheTtl", type=JsonType.STRING, values=("5m", "1h"), since=Version(2, 1, 242),
        topic=Topic.MODEL, in_schemastore=False)
    switchModelsOnFlag = SettingInfo(
        "switchModelsOnFlag", type=JsonType.BOOLEAN, topic=Topic.MODEL, in_schemastore=False)
    syncClaudeAiPlugins = SettingInfo(
        "syncClaudeAiPlugins", scope=Scope.USER | Scope.LOCAL | Scope.MANAGED, type=JsonType.BOOLEAN,
        since=Version(2, 1, 273), topic=Topic.PLUGINS, in_schemastore=False)
    syncClaudeAiSkills = SettingInfo(
        "syncClaudeAiSkills", scope=Scope.USER | Scope.LOCAL | Scope.MANAGED, type=JsonType.BOOLEAN,
        topic=Topic.PLUGINS, in_schemastore=False)
    taskOutputMaxChars = SettingInfo(
        "taskOutputMaxChars", type=JsonType.INTEGER, since=Version(2, 1, 261), removed=Version(2, 1, 277),
        topic=Topic.MEMORY, in_schemastore=False)
    terminalTitleFromRename = SettingInfo(
        "terminalTitleFromRename", type=JsonType.BOOLEAN, default=True, topic=Topic.INTERFACE, in_schemastore=False)
    timeFormat = SettingInfo(
        "timeFormat", type=JsonType.STRING, default="auto", values=("auto", "12-hour", "24-hour", "24-hour-utc"),
        since=Version(2, 1, 257), topic=Topic.INTERFACE, in_schemastore=False)
    timeZone = SettingInfo(
        "timeZone", type=JsonType.STRING, since=Version(2, 1, 257), topic=Topic.INTERFACE, in_schemastore=False)
    ultracode = SettingInfo("ultracode", type=JsonType.BOOLEAN, topic=Topic.MODEL, in_schemastore=False)


NESTED_SETTINGS: dict[str, SettingInfo] = {info.key: info for info in (
    SettingInfo("attribution.commit", type=JsonType.STRING, topic=Topic.GIT),
    SettingInfo("attribution.pr", type=JsonType.STRING, topic=Topic.GIT),
    SettingInfo(
        "attribution.sessionUrl", type=JsonType.BOOLEAN, default=True, since=Version(2, 1, 183), topic=Topic.GIT),
    SettingInfo(
        "autoMode.classifyAllShell", scope=Scope.USER | Scope.MANAGED, type=JsonType.BOOLEAN, default=False,
        since=Version(2, 1, 193), topic=Topic.PERMISSIONS),
    SettingInfo("permissions.additionalDirectories", type=JsonType.ARRAY, topic=Topic.PERMISSIONS),
    SettingInfo("permissions.allow", type=JsonType.ARRAY, topic=Topic.PERMISSIONS),
    SettingInfo("permissions.ask", type=JsonType.ARRAY, topic=Topic.PERMISSIONS),
    SettingInfo(
        "permissions.blockReadsOutsideWorkingDirectories", type=JsonType.BOOLEAN, since=Version(2, 1, 257),
        topic=Topic.PERMISSIONS, in_schemastore=False),
    SettingInfo(
        "permissions.defaultMode", type=JsonType.STRING,
        values=("acceptEdits", "bypassPermissions", "default", "delegate", "dontAsk", "plan", "auto", "manual"),
        topic=Topic.PERMISSIONS),
    SettingInfo("permissions.deny", type=JsonType.ARRAY, topic=Topic.PERMISSIONS),
    SettingInfo(
        "permissions.disableBypassPermissionsMode", type=JsonType.STRING, values=("disable",), topic=Topic.PERMISSIONS),
    SettingInfo("policyHelper.path", scope=Scope.MANAGED, type=JsonType.STRING, topic=Topic.ENTERPRISE),
    SettingInfo("policyHelper.refreshIntervalMs", scope=Scope.MANAGED, type=JsonType.INTEGER, topic=Topic.ENTERPRISE),
    SettingInfo(
        "policyHelper.timeoutMs", scope=Scope.MANAGED, type=JsonType.INTEGER, default=10000, topic=Topic.ENTERPRISE),
    SettingInfo("remote.defaultEnvironmentId", type=JsonType.STRING, topic=Topic.REMOTE, in_schemastore=False),
    SettingInfo(
        "sandbox.allowAppleEvents", scope=Scope.USER | Scope.MANAGED, type=JsonType.BOOLEAN, default=False,
        topic=Topic.SANDBOX),
    SettingInfo(
        "sandbox.allowNestedUserNamespaces", scope=Scope.USER | Scope.MANAGED, type=JsonType.BOOLEAN, default=False,
        since=Version(2, 1, 305), topic=Topic.SANDBOX, in_schemastore=False),
    SettingInfo("sandbox.allowUnsandboxedCommands", type=JsonType.BOOLEAN, default=True, topic=Topic.SANDBOX),
    SettingInfo("sandbox.autoAllowBashIfSandboxed", type=JsonType.BOOLEAN, default=True, topic=Topic.SANDBOX),
    SettingInfo(
        "sandbox.bwrapPath", scope=Scope.MANAGED, type=JsonType.STRING, since=Version(2, 1, 133), topic=Topic.SANDBOX),
    SettingInfo("sandbox.credentials", type=JsonType.OBJECT, since=Version(2, 1, 187), topic=Topic.SANDBOX),
    SettingInfo(
        "sandbox.credentials.allowPlaintextInject", scope=Scope.USER | Scope.MANAGED, type=JsonType.BOOLEAN,
        default=False, topic=Topic.SANDBOX),
    SettingInfo(
        "sandbox.credentials.awsPairs", scope=Scope.USER | Scope.MANAGED, type=JsonType.ARRAY, since=Version(2, 1, 224),
        topic=Topic.SANDBOX, in_schemastore=False),
    SettingInfo("sandbox.credentials.envVars", type=JsonType.ARRAY, topic=Topic.SANDBOX),
    SettingInfo("sandbox.credentials.files", type=JsonType.ARRAY, topic=Topic.SANDBOX),
    SettingInfo(
        "sandbox.credentials.sigv4", scope=Scope.USER | Scope.MANAGED, type=JsonType.OBJECT, since=Version(2, 1, 224),
        topic=Topic.SANDBOX, in_schemastore=False),
    SettingInfo("sandbox.enabled", type=JsonType.BOOLEAN, default=False, topic=Topic.SANDBOX),
    SettingInfo("sandbox.enableWeakerNestedSandbox", type=JsonType.BOOLEAN, default=False, topic=Topic.SANDBOX),
    SettingInfo(
        "sandbox.enableWeakerNetworkIsolation", type=JsonType.BOOLEAN, default=False, since=Version(2, 1, 69),
        topic=Topic.SANDBOX),
    SettingInfo("sandbox.excludedCommands", type=JsonType.ARRAY, topic=Topic.SANDBOX),
    SettingInfo(
        "sandbox.failIfUnavailable", type=JsonType.BOOLEAN, default=False, since=Version(2, 1, 83),
        topic=Topic.SANDBOX),
    SettingInfo("sandbox.filesystem", type=JsonType.OBJECT, topic=Topic.SANDBOX),
    SettingInfo(
        "sandbox.filesystem.allowManagedReadPathsOnly", scope=Scope.MANAGED, type=JsonType.BOOLEAN, default=False,
        topic=Topic.SANDBOX),
    SettingInfo("sandbox.filesystem.allowRead", type=JsonType.ARRAY, topic=Topic.SANDBOX),
    SettingInfo("sandbox.filesystem.allowWrite", type=JsonType.ARRAY, topic=Topic.SANDBOX),
    SettingInfo("sandbox.filesystem.denyRead", type=JsonType.ARRAY, topic=Topic.SANDBOX),
    SettingInfo("sandbox.filesystem.denyWrite", type=JsonType.ARRAY, topic=Topic.SANDBOX),
    SettingInfo(
        "sandbox.filesystem.disabled", scope=Scope.USER | Scope.MANAGED, type=JsonType.BOOLEAN, default=False,
        since=Version(2, 1, 216), topic=Topic.SANDBOX),
    SettingInfo("sandbox.ignoreViolations", type=JsonType.OBJECT, topic=Topic.SANDBOX),
    SettingInfo("sandbox.network", type=JsonType.OBJECT, topic=Topic.SANDBOX),
    SettingInfo("sandbox.network.allowAllUnixSockets", type=JsonType.BOOLEAN, default=False, topic=Topic.SANDBOX),
    SettingInfo("sandbox.network.allowedDomains", type=JsonType.ARRAY, topic=Topic.SANDBOX),
    SettingInfo("sandbox.network.allowLocalBinding", type=JsonType.BOOLEAN, default=False, topic=Topic.SANDBOX),
    SettingInfo("sandbox.network.allowMachLookup", type=JsonType.ARRAY, topic=Topic.SANDBOX),
    SettingInfo(
        "sandbox.network.allowManagedDomainsOnly", scope=Scope.MANAGED, type=JsonType.BOOLEAN, default=False,
        topic=Topic.SANDBOX),
    SettingInfo("sandbox.network.allowUnixSockets", type=JsonType.ARRAY, topic=Topic.SANDBOX),
    SettingInfo("sandbox.network.deniedDomains", type=JsonType.ARRAY, since=Version(2, 1, 113), topic=Topic.SANDBOX),
    SettingInfo("sandbox.network.httpProxyPort", type=JsonType.INTEGER, topic=Topic.SANDBOX),
    SettingInfo("sandbox.network.socksProxyPort", type=JsonType.INTEGER, topic=Topic.SANDBOX),
    SettingInfo(
        "sandbox.network.strictAllowlist", scope=Scope.USER | Scope.MANAGED, type=JsonType.BOOLEAN, default=False,
        since=Version(2, 1, 219), topic=Topic.SANDBOX),
    SettingInfo(
        "sandbox.network.tlsTerminate", scope=Scope.USER | Scope.MANAGED, type=JsonType.OBJECT, topic=Topic.SANDBOX),
    SettingInfo("sandbox.ripgrep", scope=Scope.USER | Scope.MANAGED, type=JsonType.OBJECT, topic=Topic.SANDBOX),
    SettingInfo(
        "sandbox.socatPath", scope=Scope.MANAGED, type=JsonType.STRING, since=Version(2, 1, 133), topic=Topic.SANDBOX),
    SettingInfo("strictPluginOnlyCustomization.agents", scope=Scope.MANAGED, topic=Topic.PLUGINS, in_schemastore=False),
    SettingInfo("strictPluginOnlyCustomization.hooks", scope=Scope.MANAGED, topic=Topic.PLUGINS, in_schemastore=False),
    SettingInfo("strictPluginOnlyCustomization.mcp", scope=Scope.MANAGED, topic=Topic.PLUGINS, in_schemastore=False),
    SettingInfo("strictPluginOnlyCustomization.skills", scope=Scope.MANAGED, topic=Topic.PLUGINS, in_schemastore=False),
    SettingInfo(
        "worktree.baseRef", type=JsonType.STRING, default="fresh", values=("fresh", "head"), since=Version(2, 1, 133),
        topic=Topic.AGENTS),
    SettingInfo(
        "worktree.bgIsolation", type=JsonType.STRING, default="worktree", values=("worktree", "none"),
        topic=Topic.AGENTS),
    SettingInfo("worktree.location", scope=Scope.USER, type=JsonType.STRING, topic=Topic.AGENTS, in_schemastore=False),
    SettingInfo("worktree.sparsePaths", type=JsonType.ARRAY, since=Version(2, 1, 76), topic=Topic.AGENTS),
    SettingInfo("worktree.symlinkDirectories", type=JsonType.ARRAY, topic=Topic.AGENTS),
    SettingInfo(
        "sandbox.enabledPlatforms", scope=Scope.MANAGED, type=JsonType.ARRAY,
        values=("macos", "linux", "wsl", "windows"), in_docs=False),
)}


def setting_info(path: str) -> SettingInfo | None:
    """최상위 키 또는 중첩 경로("sandbox.bwrapPath")의 SettingInfo. 모르는 경로는 None."""
    member = SettingKey._value2member_map_.get(path)
    return member.info if isinstance(member, SettingKey) else NESTED_SETTINGS.get(path)


__all__ = ["KeyEnum", "SettingInfo", "SettingKey", "EnvVar", "NESTED_SETTINGS", "setting_info"]
