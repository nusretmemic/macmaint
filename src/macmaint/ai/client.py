"""OpenAI API client for system analysis."""
import json
from typing import Dict, List, Optional
from openai import OpenAI

from macmaint.ai.prompts import create_analysis_prompt
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
    
    def analyze_system(self, metrics: Dict) -> tuple[List[Dict], str]:
        """Analyze system metrics using AI.
        
        Args:
            metrics: System metrics dictionary
        
        Returns:
            Tuple of (ai_issues, summary)
        """
        # Anonymize metrics if enabled
        if self.anonymize and self.anonymizer:
            metrics = self.anonymizer.anonymize_metrics(metrics)
        
        # Create prompt
        prompt = create_analysis_prompt(metrics)
        
        try:
            # Call OpenAI API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert macOS system administrator."},
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
