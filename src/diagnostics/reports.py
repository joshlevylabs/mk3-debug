"""Report generation for diagnostics."""

import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import asdict

from .runner import (
    DiagnosticReport, TestStatus, TestResult,
    DiagnosticFinding, RootCause, CorrectiveAction, Severity
)
from ..utils import get_logger

logger = get_logger(__name__)


def _serialize_finding(finding: DiagnosticFinding) -> Dict[str, Any]:
    """Serialize a DiagnosticFinding to a dictionary."""
    return {
        'issue': finding.issue,
        'severity': finding.severity.value,
        'root_cause': {
            'category': finding.root_cause.category,
            'description': finding.root_cause.description,
            'technical_details': finding.root_cause.technical_details,
            'evidence': finding.root_cause.evidence,
            'related_tests': finding.root_cause.related_tests,
            'firmware_relevant': finding.root_cause.firmware_relevant
        },
        'corrective_actions': [
            {
                'priority': action.priority,
                'action': action.action,
                'description': action.description,
                'responsible_party': action.responsible_party,
                'verification_steps': action.verification_steps,
                'estimated_complexity': action.estimated_complexity
            }
            for action in finding.corrective_actions
        ],
        'affected_functionality': finding.affected_functionality
    }


def _serialize_test_result(test: TestResult) -> Dict[str, Any]:
    """Serialize a TestResult with all enhanced fields."""
    result = {
        'name': test.name,
        'status': test.status.value,
        'message': test.message,
        'details': test.details,
        'duration_ms': test.duration_ms,
        'recommendations': test.recommendations
    }

    # Add enhanced fields if present
    if test.findings:
        result['findings'] = [_serialize_finding(f) for f in test.findings]

    if test.raw_data:
        result['raw_data'] = test.raw_data

    if test.test_methodology:
        result['test_methodology'] = test.test_methodology

    if test.environment_info:
        result['environment_info'] = test.environment_info

    return result


class ReportGenerator:
    """
    Generates diagnostic reports in various formats.
    """

    def __init__(self):
        pass

    def to_json(self, report: DiagnosticReport, filepath: Optional[Path] = None) -> str:
        """
        Export report to JSON format with full diagnostic details.

        Args:
            report: DiagnosticReport to export
            filepath: Optional file path to save to

        Returns:
            JSON string
        """
        # Build executive summary for developers
        failed_tests = [t for t in report.tests if t.status == TestStatus.FAILED]
        warning_tests = [t for t in report.tests if t.status == TestStatus.WARNING]

        # Collect all findings across tests
        all_findings = []
        firmware_issues = []
        for test in report.tests:
            for finding in test.findings:
                all_findings.append({
                    'test': test.name,
                    **_serialize_finding(finding)
                })
                if finding.root_cause.firmware_relevant:
                    firmware_issues.append({
                        'test': test.name,
                        'issue': finding.issue,
                        'severity': finding.severity.value,
                        'technical_details': finding.root_cause.technical_details
                    })

        data = {
            'report_version': '2.0',
            'timestamp': report.timestamp.isoformat(),
            'ip_address': report.ip_address,
            'overall_status': report.overall_status,
            'duration_ms': report.duration_ms,

            # Executive summary for quick review
            'executive_summary': {
                'total_tests': len(report.tests),
                'passed': report.summary['passed'],
                'failed': report.summary['failed'],
                'warnings': report.summary['warnings'],
                'critical_issues': len([f for f in all_findings if f.get('severity') == 'critical']),
                'firmware_relevant_issues': len(firmware_issues),
                'quick_summary': self._generate_quick_summary(report)
            },

            # Firmware team specific section
            'firmware_team_attention': {
                'has_issues': len(firmware_issues) > 0,
                'issues': firmware_issues
            },

            # All findings aggregated for easy parsing
            'all_findings': all_findings,

            # Detailed test results
            'tests': [_serialize_test_result(t) for t in report.tests],

            # Legacy summary for backward compatibility
            'summary': report.summary
        }

        json_str = json.dumps(data, indent=2, default=str)

        if filepath:
            filepath = Path(filepath)
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(json_str)
            logger.info(f"Report saved to {filepath}")

        return json_str

    def _generate_quick_summary(self, report: DiagnosticReport) -> str:
        """Generate a quick human-readable summary."""
        if report.overall_status == "healthy":
            return "All diagnostic tests passed. Device is functioning normally."

        issues = []
        for test in report.tests:
            if test.status == TestStatus.FAILED:
                issues.append(f"FAILED: {test.name} - {test.message}")
            elif test.status == TestStatus.WARNING:
                issues.append(f"WARNING: {test.name} - {test.message}")

        return " | ".join(issues) if issues else "No issues detected."

    def to_html(self, report: DiagnosticReport, filepath: Optional[Path] = None) -> str:
        """
        Export report to HTML format with comprehensive diagnostic details.

        Args:
            report: DiagnosticReport to export
            filepath: Optional file path to save to

        Returns:
            HTML string
        """
        status_colors = {
            TestStatus.PASSED: '#27ae60',
            TestStatus.FAILED: '#e74c3c',
            TestStatus.WARNING: '#f39c12',
            TestStatus.SKIPPED: '#95a5a6',
            TestStatus.ERROR: '#9b59b6',
            TestStatus.PENDING: '#3498db',
            TestStatus.RUNNING: '#3498db'
        }

        severity_colors = {
            'critical': '#e74c3c',
            'high': '#e67e22',
            'medium': '#f39c12',
            'low': '#3498db',
            'info': '#95a5a6'
        }

        overall_colors = {
            'healthy': '#27ae60',
            'minor_issues': '#f39c12',
            'problems_detected': '#e74c3c'
        }

        tests_html = ""
        for test in report.tests:
            color = status_colors.get(test.status, '#95a5a6')
            status_text = test.status.value.upper()

            # Build findings HTML with root cause analysis
            findings_html = ""
            if test.findings:
                for finding in test.findings:
                    sev_color = severity_colors.get(finding.severity.value, '#95a5a6')

                    # Build corrective actions HTML
                    actions_html = ""
                    for action in finding.corrective_actions:
                        verification_html = ""
                        if action.verification_steps:
                            verification_html = "<div class='verification-steps'><strong>Verification:</strong><ol>"
                            for step in action.verification_steps:
                                verification_html += f"<li>{step}</li>"
                            verification_html += "</ol></div>"

                        actions_html += f"""
                        <div class="action-item">
                            <div class="action-header">
                                <span class="action-priority">#{action.priority}</span>
                                <span class="action-title">{action.action}</span>
                                <span class="action-owner">{action.responsible_party}</span>
                                <span class="action-complexity complexity-{action.estimated_complexity}">{action.estimated_complexity}</span>
                            </div>
                            <div class="action-description">{action.description}</div>
                            {verification_html}
                        </div>
                        """

                    # Build evidence HTML
                    evidence_html = ""
                    if finding.root_cause.evidence:
                        evidence_html = "<div class='evidence'><strong>Evidence:</strong><ul>"
                        for ev in finding.root_cause.evidence:
                            evidence_html += f"<li>{ev}</li>"
                        evidence_html += "</ul></div>"

                    # Build affected functionality HTML
                    affected_html = ""
                    if finding.affected_functionality:
                        affected_html = "<div class='affected'><strong>Affected Functionality:</strong><ul>"
                        for af in finding.affected_functionality:
                            affected_html += f"<li>{af}</li>"
                        affected_html += "</ul></div>"

                    firmware_badge = ""
                    if finding.root_cause.firmware_relevant:
                        firmware_badge = '<span class="firmware-badge">FIRMWARE TEAM</span>'

                    findings_html += f"""
                    <div class="finding">
                        <div class="finding-header">
                            <span class="severity-badge" style="background-color: {sev_color};">{finding.severity.value.upper()}</span>
                            <span class="finding-title">{finding.issue}</span>
                            {firmware_badge}
                        </div>

                        <div class="root-cause">
                            <h4>Root Cause Analysis</h4>
                            <div class="cause-category"><strong>Category:</strong> {finding.root_cause.category}</div>
                            <div class="cause-description">{finding.root_cause.description}</div>
                            <div class="cause-technical">
                                <strong>Technical Details:</strong>
                                <p>{finding.root_cause.technical_details}</p>
                            </div>
                            {evidence_html}
                        </div>

                        <div class="corrective-actions">
                            <h4>Corrective Actions (Priority Order)</h4>
                            {actions_html}
                        </div>

                        {affected_html}
                    </div>
                    """

            # Legacy recommendations (fallback)
            recommendations_html = ""
            if test.recommendations and not test.findings:
                recommendations_html = "<div class='recommendations'><strong>Recommendations:</strong><ul>"
                for rec in test.recommendations:
                    recommendations_html += f"<li>{rec}</li>"
                recommendations_html += "</ul></div>"

            # Test methodology
            methodology_html = ""
            if test.test_methodology:
                methodology_html = f"<div class='methodology'><strong>Test Methodology:</strong> {test.test_methodology}</div>"

            details_html = ""
            if test.details:
                details_html = f"<details class='details-section'><summary>Raw Test Data</summary><pre class='details'>{json.dumps(test.details, indent=2)}</pre></details>"

            raw_data_html = ""
            if test.raw_data:
                raw_data_html = f"<details class='details-section'><summary>Developer Raw Data</summary><pre class='details'>{json.dumps(test.raw_data, indent=2)}</pre></details>"

            tests_html += f"""
            <div class="test">
                <div class="test-header">
                    <span class="test-name">{test.name}</span>
                    <span class="test-status" style="background-color: {color};">{status_text}</span>
                </div>
                <div class="test-message">{test.message}</div>
                {methodology_html}
                {findings_html}
                {recommendations_html}
                {details_html}
                {raw_data_html}
            </div>
            """

        overall_color = overall_colors.get(report.overall_status, '#95a5a6')

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MK3 Diagnostic Report - {report.ip_address}</title>
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: #1a1a2e;
            color: #eee;
            line-height: 1.6;
            padding: 20px;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
        }}
        header {{
            text-align: center;
            padding: 30px 0;
            border-bottom: 2px solid #333;
            margin-bottom: 30px;
        }}
        h1 {{
            color: #3498db;
            font-size: 2em;
            margin-bottom: 10px;
        }}
        .meta {{
            color: #888;
            font-size: 0.9em;
        }}
        .summary {{
            background: #16213e;
            padding: 25px;
            border-radius: 10px;
            margin-bottom: 30px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 20px;
        }}
        .summary-item {{
            text-align: center;
        }}
        .summary-value {{
            font-size: 2.5em;
            font-weight: bold;
        }}
        .summary-label {{
            color: #888;
            font-size: 0.9em;
        }}
        .passed {{ color: #27ae60; }}
        .failed {{ color: #e74c3c; }}
        .warnings {{ color: #f39c12; }}
        .overall {{
            background: {overall_color};
            color: white;
            padding: 15px 30px;
            border-radius: 8px;
            text-align: center;
            font-size: 1.2em;
            font-weight: bold;
            margin-bottom: 30px;
        }}
        .test {{
            background: #16213e;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 15px;
        }}
        .test-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }}
        .test-name {{
            font-size: 1.2em;
            font-weight: bold;
        }}
        .test-status {{
            padding: 5px 15px;
            border-radius: 20px;
            color: white;
            font-size: 0.8em;
            font-weight: bold;
        }}
        .test-message {{
            color: #ccc;
            margin-bottom: 10px;
        }}
        .details {{
            background: #0f0f23;
            padding: 15px;
            border-radius: 5px;
            font-size: 0.85em;
            overflow-x: auto;
            margin: 10px 0;
        }}
        .recommendations {{
            background: #1a1a2e;
            padding: 15px;
            border-left: 3px solid #3498db;
            margin-top: 10px;
        }}
        .recommendations ul {{
            margin-left: 20px;
            margin-top: 10px;
        }}
        .recommendations li {{
            margin-bottom: 5px;
        }}
        .methodology {{
            font-size: 0.85em;
            color: #888;
            font-style: italic;
            margin: 10px 0;
            padding: 8px;
            background: #0f0f23;
            border-radius: 4px;
        }}
        .finding {{
            background: #1a1a2e;
            border: 1px solid #333;
            border-radius: 8px;
            margin: 15px 0;
            padding: 20px;
        }}
        .finding-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }}
        .severity-badge {{
            padding: 4px 12px;
            border-radius: 12px;
            color: white;
            font-size: 0.75em;
            font-weight: bold;
            text-transform: uppercase;
        }}
        .finding-title {{
            font-size: 1.1em;
            font-weight: bold;
            color: #fff;
        }}
        .firmware-badge {{
            background: #9b59b6;
            color: white;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.7em;
            font-weight: bold;
        }}
        .root-cause {{
            background: #0f0f23;
            padding: 15px;
            border-radius: 6px;
            margin: 10px 0;
        }}
        .root-cause h4 {{
            color: #3498db;
            margin-bottom: 10px;
            border-bottom: 1px solid #333;
            padding-bottom: 5px;
        }}
        .cause-category {{
            margin-bottom: 8px;
            color: #ccc;
        }}
        .cause-description {{
            margin-bottom: 12px;
            line-height: 1.6;
        }}
        .cause-technical {{
            background: #16213e;
            padding: 12px;
            border-radius: 4px;
            margin: 10px 0;
            border-left: 3px solid #e74c3c;
        }}
        .cause-technical p {{
            margin: 8px 0 0 0;
            font-family: monospace;
            font-size: 0.9em;
            line-height: 1.5;
        }}
        .evidence {{
            margin-top: 12px;
        }}
        .evidence ul {{
            margin-left: 20px;
            margin-top: 8px;
        }}
        .evidence li {{
            margin-bottom: 4px;
            font-size: 0.9em;
            color: #aaa;
        }}
        .corrective-actions {{
            margin-top: 15px;
        }}
        .corrective-actions h4 {{
            color: #27ae60;
            margin-bottom: 10px;
            border-bottom: 1px solid #333;
            padding-bottom: 5px;
        }}
        .action-item {{
            background: #16213e;
            border-radius: 6px;
            padding: 12px;
            margin: 10px 0;
            border-left: 3px solid #27ae60;
        }}
        .action-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 8px;
            flex-wrap: wrap;
        }}
        .action-priority {{
            background: #27ae60;
            color: white;
            width: 24px;
            height: 24px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.8em;
            font-weight: bold;
        }}
        .action-title {{
            font-weight: bold;
            flex: 1;
        }}
        .action-owner {{
            background: #2c3e50;
            padding: 3px 8px;
            border-radius: 10px;
            font-size: 0.75em;
            color: #bbb;
        }}
        .action-complexity {{
            padding: 3px 8px;
            border-radius: 10px;
            font-size: 0.75em;
            font-weight: bold;
        }}
        .complexity-low {{ background: #27ae60; color: white; }}
        .complexity-medium {{ background: #f39c12; color: white; }}
        .complexity-high {{ background: #e74c3c; color: white; }}
        .action-description {{
            font-size: 0.9em;
            color: #ccc;
            margin-bottom: 10px;
        }}
        .verification-steps {{
            background: #0f0f23;
            padding: 10px;
            border-radius: 4px;
            font-size: 0.85em;
        }}
        .verification-steps ol {{
            margin-left: 20px;
            margin-top: 8px;
        }}
        .verification-steps li {{
            margin-bottom: 4px;
        }}
        .affected {{
            margin-top: 12px;
            padding: 10px;
            background: #2c1810;
            border-radius: 4px;
            border-left: 3px solid #e74c3c;
        }}
        .affected ul {{
            margin-left: 20px;
            margin-top: 8px;
        }}
        .affected li {{
            margin-bottom: 4px;
            font-size: 0.9em;
        }}
        .details-section {{
            margin: 10px 0;
        }}
        .details-section summary {{
            cursor: pointer;
            color: #3498db;
            font-size: 0.9em;
        }}
        .details-section summary:hover {{
            text-decoration: underline;
        }}
        footer {{
            text-align: center;
            padding: 20px;
            color: #666;
            margin-top: 30px;
            border-top: 1px solid #333;
        }}
        @media print {{
            body {{
                background: white;
                color: black;
            }}
            .test, .summary {{
                background: #f5f5f5;
                border: 1px solid #ddd;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>MK3 Amplifier Diagnostic Report</h1>
            <div class="meta">
                <p>Target: <strong>{report.ip_address}</strong></p>
                <p>Generated: {report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>Duration: {report.duration_ms:.0f}ms</p>
            </div>
        </header>

        <div class="overall">
            Overall Status: {report.overall_status.replace('_', ' ').upper()}
        </div>

        <div class="summary">
            <div class="summary-item">
                <div class="summary-value passed">{report.summary['passed']}</div>
                <div class="summary-label">Passed</div>
            </div>
            <div class="summary-item">
                <div class="summary-value warnings">{report.summary['warnings']}</div>
                <div class="summary-label">Warnings</div>
            </div>
            <div class="summary-item">
                <div class="summary-value failed">{report.summary['failed']}</div>
                <div class="summary-label">Failed</div>
            </div>
        </div>

        <h2 style="margin-bottom: 20px;">Test Results</h2>

        {tests_html}

        <footer>
            <p>Generated by MK3 Amplifier Network Diagnostic Tool</p>
            <p>Sonance - Architectural Audio Systems</p>
        </footer>
    </div>
</body>
</html>
"""

        if filepath:
            filepath = Path(filepath)
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html)
            logger.info(f"HTML report saved to {filepath}")

        return html

    def to_text(self, report: DiagnosticReport, filepath: Optional[Path] = None) -> str:
        """
        Export report to plain text format.

        Args:
            report: DiagnosticReport to export
            filepath: Optional file path to save to

        Returns:
            Text string
        """
        lines = [
            "=" * 60,
            "MK3 AMPLIFIER DIAGNOSTIC REPORT",
            "=" * 60,
            "",
            f"Target IP:      {report.ip_address}",
            f"Timestamp:      {report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Duration:       {report.duration_ms:.0f}ms",
            f"Overall Status: {report.overall_status.replace('_', ' ').upper()}",
            "",
            "-" * 60,
            "SUMMARY",
            "-" * 60,
            f"  Passed:   {report.summary['passed']}",
            f"  Warnings: {report.summary['warnings']}",
            f"  Failed:   {report.summary['failed']}",
            "",
            "-" * 60,
            "TEST RESULTS",
            "-" * 60,
        ]

        for test in report.tests:
            status_icon = {
                TestStatus.PASSED: "[PASS]",
                TestStatus.FAILED: "[FAIL]",
                TestStatus.WARNING: "[WARN]",
                TestStatus.SKIPPED: "[SKIP]",
                TestStatus.ERROR: "[ERR ]"
            }.get(test.status, "[????]")

            lines.append(f"\n{status_icon} {test.name}")
            lines.append(f"  {test.message}")

            # Show test methodology if available
            if test.test_methodology:
                lines.append(f"  Methodology: {test.test_methodology}")

            # Show detailed findings with root cause analysis
            if test.findings:
                for finding in test.findings:
                    lines.append("")
                    lines.append(f"  >>> FINDING: {finding.issue}")
                    lines.append(f"      Severity: {finding.severity.value.upper()}")
                    if finding.root_cause.firmware_relevant:
                        lines.append("      [FIRMWARE TEAM ATTENTION REQUIRED]")

                    lines.append("")
                    lines.append("      ROOT CAUSE ANALYSIS:")
                    lines.append(f"        Category: {finding.root_cause.category}")
                    lines.append(f"        Description: {finding.root_cause.description}")
                    lines.append("")
                    lines.append("        Technical Details:")
                    # Wrap technical details
                    tech_details = finding.root_cause.technical_details
                    wrapped = [tech_details[i:i+70] for i in range(0, len(tech_details), 70)]
                    for line in wrapped:
                        lines.append(f"          {line}")

                    if finding.root_cause.evidence:
                        lines.append("")
                        lines.append("        Evidence:")
                        for ev in finding.root_cause.evidence:
                            lines.append(f"          - {ev}")

                    if finding.corrective_actions:
                        lines.append("")
                        lines.append("      CORRECTIVE ACTIONS:")
                        for action in finding.corrective_actions:
                            lines.append(f"        #{action.priority} [{action.responsible_party}] [{action.estimated_complexity}]")
                            lines.append(f"           {action.action}")
                            lines.append(f"           {action.description}")
                            if action.verification_steps:
                                lines.append("           Verification:")
                                for i, step in enumerate(action.verification_steps, 1):
                                    lines.append(f"             {i}. {step}")

                    if finding.affected_functionality:
                        lines.append("")
                        lines.append("      AFFECTED FUNCTIONALITY:")
                        for af in finding.affected_functionality:
                            lines.append(f"        - {af}")

            # Fallback to simple recommendations if no findings
            elif test.recommendations:
                lines.append("  Recommendations:")
                for rec in test.recommendations:
                    lines.append(f"    - {rec}")

        lines.extend([
            "",
            "=" * 60,
            "End of Report",
            "=" * 60
        ])

        text = "\n".join(lines)

        if filepath:
            filepath = Path(filepath)
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(text)
            logger.info(f"Text report saved to {filepath}")

        return text
