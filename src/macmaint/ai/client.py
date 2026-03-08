"""OpenAI API client for system analysis."""
import json
from typing import Dict, List, Optional
from openai import OpenAI

from macmaint.ai.prompts import (
    create_analysis_prompt,
    create_conversational_prompt,
    create_explain_prompt,
    create_cleanup_prompt,
    create_proactive_prompt,
    get_role_system_prompt,
    AIRole
)
from macmaint.ai.anonymizer import DataAnonymizer
from macmaint.models.issue import Issue, IssueSeverity, IssueCategory


class AIClient:
    """Client for AI-powered system analysis."""
    
    def __init__(self, api_key: str, model: str = "gpt-4-turbo", anonymize: bool = True):
        """Initialize AI client.
        
        Args:
            api_key: OpenAI API key
            model: Model to use for analysis
            anonymize: Whether to anonymize data before sending
        """
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.anonymize = anonymize
        self.anonymizer = DataAnonymizer() if anonymize else None
    
    def analyze_system(self, metrics: Dict, role: AIRole = AIRole.GENERAL) -> tuple[List[Dict], str]:
        """Analyze system metrics using AI.
        
        Args:
            metrics: System metrics dictionary
            role: AI role/persona to use for analysis
        
        Returns:
            Tuple of (ai_issues, summary)
        """
        # Anonymize metrics if enabled
        if self.anonymize and self.anonymizer:
            metrics = self.anonymizer.anonymize_metrics(metrics)
        
        # Create prompt
        prompt = create_analysis_prompt(metrics)
        system_prompt = get_role_system_prompt(role)
        
        try:
            # Call OpenAI API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # Lower temperature for more consistent analysis
                max_tokens=2000,
                response_format={"type": "json_object"}
            )
            
            # Parse response
            content = response.choices[0].message.content
            result = json.loads(content)
            
            ai_issues = result.get("issues", [])
            summary = result.get("summary", "Analysis complete.")
            
            return ai_issues, summary
            
        except Exception as e:
            # Return empty results on error, don't crash
            return [], f"AI analysis failed: {str(e)}"
    
    def ask_question(self, question: str, metrics: Dict, issues: List = None, profile_summary: Dict = None) -> str:
        """Answer a natural language question about the system.
        
        Args:
            question: User's question
            metrics: Current system metrics
            issues: List of current issues (optional)
            profile_summary: User profile summary (optional)
        
        Returns:
            AI response string
        """
        # Anonymize metrics if enabled
        if self.anonymize and self.anonymizer:
            metrics = self.anonymizer.anonymize_metrics(metrics)
        
        prompt = create_conversational_prompt(question, metrics, issues, profile_summary)
        system_prompt = get_role_system_prompt(AIRole.GENERAL)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,  # More conversational
                max_tokens=1000
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            return f"Sorry, I couldn't process your question: {str(e)}"
    
    def explain_issue(self, issue: Issue, metrics: Dict, profile_summary: Dict = None) -> str:
        """Provide detailed explanation of a specific issue.
        
        Args:
            issue: Issue to explain
            metrics: Current system metrics
            profile_summary: User profile summary (optional)
        
        Returns:
            Detailed explanation string
        """
        # Anonymize metrics if enabled
        if self.anonymize and self.anonymizer:
            metrics = self.anonymizer.anonymize_metrics(metrics)
        
        issue_dict = {
            "id": issue.id,
            "title": issue.title,
            "description": issue.description,
            "severity": str(issue.severity),
            "category": str(issue.category),
            "metrics": issue.metrics
        }
        
        prompt = create_explain_prompt(issue_dict, metrics, profile_summary)
        system_prompt = get_role_system_prompt(AIRole.TROUBLESHOOTER)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=1500
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            return f"Sorry, I couldn't explain this issue: {str(e)}"
    
    def analyze_cleanup_safety(self, items: List[Dict], user_profile: Dict) -> Dict:
        """Analyze safety of deleting files/directories.
        
        Args:
            items: List of items to analyze (path, size, age, etc.)
            user_profile: User preferences and patterns
        
        Returns:
            Analysis results with risk levels
        """
        prompt = create_cleanup_prompt(items, user_profile)
        system_prompt = get_role_system_prompt(AIRole.STORAGE)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,  # Very conservative for safety analysis
                max_tokens=2000,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            return json.loads(content)
            
        except Exception as e:
            return {
                "items": [],
                "summary": {"error": str(e)}
            }
    
    def get_proactive_insights(self, metrics: Dict, issues: List, snapshots: List, profile_summary: Dict) -> str:
        """Get proactive insights and predictions.
        
        Args:
            metrics: Current system metrics
            issues: Current issues list
            snapshots: Historical snapshots
            profile_summary: User preferences and patterns
        
        Returns:
            Insights and predictions as markdown string
        """
        # Anonymize metrics if enabled
        if self.anonymize and self.anonymizer:
            metrics = self.anonymizer.anonymize_metrics(metrics)
        
        prompt = create_proactive_prompt(metrics, issues, snapshots, profile_summary)
        system_prompt = get_role_system_prompt(AIRole.MAINTENANCE)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4,
                max_tokens=2000
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            return f"Sorry, I couldn't generate insights: {str(e)}"
    
    def enrich_issues(self, existing_issues: List[Issue], ai_issues: List[Dict]) -> List[Issue]:
        """Enrich existing issues with AI recommendations.
        
        Args:
            existing_issues: Issues detected by modules
            ai_issues: Issues from AI analysis
        
        Returns:
            Enriched issues list
        """
        # Create a map of existing issues by category
        issue_map = {issue.category.value: issue for issue in existing_issues}
        
        # Add AI recommendations to matching issues
        for ai_issue in ai_issues:
            category = ai_issue.get("category", "system")
            recommendation = ai_issue.get("recommendation", "")
            
            # Find matching issue by category
            if category in issue_map:
                issue = issue_map[category]
                if recommendation:
                    issue.ai_recommendation = recommendation
        
        # Optionally create new issues from AI that don't match existing ones
        # For now, we'll just enrich existing ones
        
        return existing_issues
