"""AI prompts for system analysis."""
from enum import Enum
from typing import Dict


class AIRole(str, Enum):
    """AI persona roles for different analysis types."""
    GENERAL = "general"
    PERFORMANCE = "performance"
    SECURITY = "security"
    STORAGE = "storage"
    MAINTENANCE = "maintenance"
    TROUBLESHOOTER = "troubleshooter"


# Role-specific system prompts
ROLE_PROMPTS = {
    AIRole.GENERAL: """You are MacMaint Assistant, a friendly and knowledgeable macOS system expert. 
You help users understand their system's health and provide clear, actionable advice in a conversational tone.
Focus on explaining things simply without being condescending.""",

    AIRole.PERFORMANCE: """You are a macOS performance optimization specialist. 
Your expertise is in identifying bottlenecks, memory issues, CPU problems, and making systems run faster.
Provide specific, technical recommendations for improving system performance.""",

    AIRole.SECURITY: """You are a macOS security analyst.
Focus on identifying security risks, suspicious processes, network vulnerabilities, and providing hardening recommendations.
Be thorough but don't create unnecessary alarm.""",

    AIRole.STORAGE: """You are a disk space management expert for macOS.
Specialize in identifying storage hogs, cache issues, duplicate files, and helping users reclaim disk space safely.
Explain what can be safely deleted and what should be kept.""",

    AIRole.MAINTENANCE: """You are a proactive system maintenance advisor for macOS.
Identify preventive maintenance tasks, predict future issues, and provide scheduling recommendations.
Think long-term about system health.""",

    AIRole.TROUBLESHOOTER: """You are an expert macOS troubleshooter and problem solver.
Excel at root cause analysis, explaining complex technical issues in simple terms, and providing step-by-step solutions.
Be methodical and thorough."""
}


SYSTEM_ANALYSIS_PROMPT = """You are an expert macOS system administrator and performance analyst. 
Your task is to analyze system metrics and provide actionable recommendations for maintenance and optimization.

**Guidelines:**
1. Focus on the most impactful issues first (critical > warning > info)
2. Provide specific, actionable recommendations
3. Consider user experience and system performance
4. Be conservative with recommendations that could affect stability
5. Explain the "why" behind each recommendation

**Analysis Format:**
For each issue you identify, provide:
- Severity: critical, warning, or info
- Title: Brief description (one line)
- Recommendation: Specific action to take
- Impact: Expected benefit from taking the action

**System Metrics:**
{metrics}

Analyze the above metrics and provide your recommendations in JSON format:
{{
  "issues": [
    {{
      "severity": "critical|warning|info",
      "category": "disk|memory|cpu|system|network",
      "title": "Brief issue description",
      "recommendation": "Specific actionable recommendation",
      "reasoning": "Why this is an issue and why this action helps"
    }}
  ],
  "summary": "Overall system health assessment (2-3 sentences)"
}}
"""


CONVERSATIONAL_PROMPT = """You are MacMaint Assistant, a helpful and friendly macOS system expert.
A user has a question about their Mac. Use the provided system metrics to give an accurate, helpful answer.

**Guidelines:**
- Be conversational and friendly, not overly technical unless asked
- Reference specific metrics when relevant
- Provide actionable advice when appropriate
- If you don't have enough information, say so
- Keep responses concise but thorough (2-4 paragraphs max)

**Current System Metrics:**
{metrics}

**User Question:**
{question}

Provide your response:"""


EXPLAIN_ISSUE_PROMPT = """You are MacMaint Assistant explaining a specific system issue to a user.

**Your Goal:**
Provide a comprehensive but friendly explanation of the issue, why it matters, and what can be done about it.

**Structure your response with:**
1. **What's happening:** Plain English explanation of the issue
2. **Why it matters:** Impact on system and user experience  
3. **What causes this:** Common reasons this happens
4. **What you can do:** Step-by-step recommendations
5. **Prevention:** How to avoid this in the future

**Issue Details:**
{issue}

**Current System Context:**
{metrics}

Provide your detailed explanation:"""


CLEANUP_ANALYSIS_PROMPT = """You are a careful and methodical macOS storage analyst.
Analyze the provided files and directories and assess their safety for deletion.

**Your Task:**
Evaluate each item and classify it by risk level, explaining your reasoning.

**Risk Levels:**
- **SAFE**: Can be deleted without any issues (caches, temp files, duplicates)
- **LOW_RISK**: Usually safe but might cause minor inconvenience (logs, old downloads)
- **MEDIUM_RISK**: May require caution (app data, preferences that will reset)
- **HIGH_RISK**: Should not be deleted without user confirmation (documents, important configs)
- **CRITICAL**: Never delete (system files, active app data, user documents)

**Items to Analyze:**
{items}

**User Context:**
{user_profile}

Provide analysis in JSON format:
{{
  "items": [
    {{
      "path": "file or directory path",
      "risk_level": "SAFE|LOW_RISK|MEDIUM_RISK|HIGH_RISK|CRITICAL",
      "size_mb": 123.45,
      "reasoning": "Why this risk level",
      "recommendation": "Delete|Keep|Review"
    }}
  ],
  "summary": {{
    "total_safe_to_delete_gb": 0.0,
    "total_low_risk_gb": 0.0,
    "overall_recommendation": "Brief summary of what can be safely cleaned"
  }}
}}"""


PROACTIVE_INSIGHTS_PROMPT = """You are a proactive system health advisor for macOS.
Analyze trends and current state to predict future issues and provide preventive recommendations.

**Your Task:**
Look at current metrics and historical trends to:
1. Identify patterns that could lead to future problems
2. Predict when issues might occur
3. Suggest preventive maintenance
4. Recommend optimal timing for actions

**Current Metrics:**
{metrics}

**Historical Trends (last 7 days):**
{trends}

**User Profile:**
{user_profile}

Provide insights in JSON format:
{{
  "predictions": [
    {{
      "issue": "What problem might occur",
      "likelihood": "high|medium|low",
      "timeframe": "when it might happen (e.g., '2-3 weeks')",
      "prevention": "What to do now to prevent it",
      "priority": "high|medium|low"
    }}
  ],
  "maintenance_schedule": {{
    "weekly": ["task 1", "task 2"],
    "monthly": ["task 1", "task 2"],
    "quarterly": ["task 1", "task 2"]
  }},
  "optimization_opportunities": [
    {{
      "area": "performance|storage|security|etc",
      "recommendation": "specific action",
      "expected_benefit": "what will improve"
    }}
  ],
  "summary": "Overall health trajectory and key recommendations"
}}"""


def create_analysis_prompt(metrics: dict) -> str:
    """Create the analysis prompt with metrics.
    
    Args:
        metrics: Anonymized system metrics
    
    Returns:
        Formatted prompt string
    """
    import json
    metrics_json = json.dumps(metrics, indent=2)
    return SYSTEM_ANALYSIS_PROMPT.format(metrics=metrics_json)


def create_conversational_prompt(question: str, metrics: dict, issues: list = None, profile_summary: dict = None) -> str:
    """Create a conversational prompt for user questions.
    
    Args:
        question: User's question
        metrics: Current system metrics
        issues: List of current issues (optional)
        profile_summary: User profile summary (optional)
    
    Returns:
        Formatted prompt string
    """
    import json
    metrics_json = json.dumps(metrics, indent=2)
    
    # Build enhanced context with issues and profile if available
    context_parts = [f"System Metrics:\n{metrics_json}"]
    
    if issues:
        issues_summary = [{"title": getattr(i, 'title', str(i)), "severity": str(getattr(i, 'severity', 'unknown'))} for i in issues[:5]]
        context_parts.append(f"\nCurrent Issues:\n{json.dumps(issues_summary, indent=2)}")
    
    if profile_summary:
        context_parts.append(f"\nUser Profile:\n{json.dumps(profile_summary, indent=2)}")
    
    full_context = "\n".join(context_parts)
    
    return CONVERSATIONAL_PROMPT.format(
        question=question,
        metrics=full_context
    )


def create_explain_prompt(issue: Dict, metrics: dict, profile_summary: dict = None) -> str:
    """Create an explanation prompt for a specific issue.
    
    Args:
        issue: Issue details
        metrics: Current system metrics
        profile_summary: User profile summary (optional)
    
    Returns:
        Formatted prompt string
    """
    import json
    issue_json = json.dumps(issue, indent=2)
    metrics_json = json.dumps(metrics, indent=2)
    
    # Add profile context if available
    context = f"Issue:\n{issue_json}\n\nSystem Metrics:\n{metrics_json}"
    if profile_summary:
        context += f"\n\nUser Profile:\n{json.dumps(profile_summary, indent=2)}"
    
    return EXPLAIN_ISSUE_PROMPT.format(
        issue=issue_json,
        metrics=context
    )


def create_cleanup_prompt(items: list, user_profile: dict) -> str:
    """Create a cleanup analysis prompt.
    
    Args:
        items: List of files/directories to analyze
        user_profile: User preferences and patterns
    
    Returns:
        Formatted prompt string
    """
    import json
    items_json = json.dumps(items, indent=2)
    profile_json = json.dumps(user_profile, indent=2)
    return CLEANUP_ANALYSIS_PROMPT.format(
        items=items_json,
        user_profile=profile_json
    )


def create_proactive_prompt(metrics: dict, issues: list, snapshots: list, profile_summary: dict) -> str:
    """Create a proactive insights prompt.
    
    Args:
        metrics: Current system metrics
        issues: Current issues list
        snapshots: Historical snapshots
        profile_summary: User preferences and patterns
    
    Returns:
        Formatted prompt string
    """
    import json
    metrics_json = json.dumps(metrics, indent=2)
    
    # Convert issues to simple format
    issues_summary = []
    for issue in issues:
        issues_summary.append({
            "title": getattr(issue, 'title', str(issue)),
            "severity": str(getattr(issue, 'severity', 'unknown'))
        })
    issues_json = json.dumps(issues_summary, indent=2)
    
    # Format snapshots as trends
    snapshots_json = json.dumps(snapshots, indent=2, default=str)
    
    profile_json = json.dumps(profile_summary, indent=2)
    
    return PROACTIVE_INSIGHTS_PROMPT.format(
        metrics=metrics_json,
        trends=f"Issues:\n{issues_json}\n\nHistorical Data:\n{snapshots_json}",
        user_profile=profile_json
    )


def get_role_system_prompt(role: AIRole) -> str:
    """Get the system prompt for a specific AI role.
    
    Args:
        role: AI role to use
    
    Returns:
        System prompt string
    """
    return ROLE_PROMPTS.get(role, ROLE_PROMPTS[AIRole.GENERAL])
