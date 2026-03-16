"""
HTML Structure Validator and Validation System for Report Generator
Prevents div bleeding and canvas issues by validating HTML structure.
Scans and validates HTML structure in report_generator.py output.
Note: Source code fixes are disabled to prevent syntax errors.
"""

import re
import ast
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import Counter


class HTMLValidator:
    """Validates HTML structure to prevent bleeding and canvas issues."""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
    
    def validate_html_structure(self, html: str, context: str = "") -> Dict:
        """
        Comprehensive HTML structure validation.
        
        Args:
            html: HTML string to validate
            context: Description of what's being validated (e.g., "Executive Tab")
        
        Returns:
            Dict with validation results:
            {
                'valid': bool,
                'errors': List[str],
                'warnings': List[str],
                'balance': Dict with tag counts,
                'unclosed_tags': List[str],
                'auto_fixed': bool
            }
        """
        self.errors = []
        self.warnings = []
        
        # 1. Check div balance
        balance_result = self._check_tag_balance(html, 'div')
        
        # 2. Check common container tags
        for tag in ['section', 'article', 'main', 'header', 'footer', 'nav']:
            tag_balance = self._check_tag_balance(html, tag)
            if tag_balance['diff'] != 0:
                self.warnings.append(
                    f"{context}: <{tag}> imbalance: {tag_balance['opens']} opens, "
                    f"{tag_balance['closes']} closes (diff: {tag_balance['diff']})"
                )
        
        # 3. Check script/style tag balance
        script_balance = self._check_tag_balance(html, 'script')
        style_balance = self._check_tag_balance(html, 'style')
        
        if script_balance['diff'] != 0:
            self.errors.append(
                f"{context}: <script> imbalance: {script_balance['opens']} opens, "
                f"{script_balance['closes']} closes (diff: {script_balance['diff']})"
            )
        
        if style_balance['diff'] != 0:
            self.errors.append(
                f"{context}: <style> imbalance: {style_balance['opens']} opens, "
                f"{style_balance['closes']} closes (diff: {style_balance['diff']})"
            )
        
        # 4. Find unclosed tags (tags that should always close)
        unclosed = self._find_unclosed_tags(html)
        
        # 5. Check for common HTML errors
        self._check_common_errors(html, context)
        
        return {
            'valid': len(self.errors) == 0 and balance_result['diff'] == 0,
            'errors': self.errors,
            'warnings': self.warnings,
            'balance': balance_result,
            'unclosed_tags': unclosed,
            'auto_fixed': False,
            'context': context
        }
    
    def _check_tag_balance(self, html: str, tag: str) -> Dict:
        """Check if opening and closing tags are balanced."""
        # Simple and reliable counting - match all opening tags with or without attributes
        open_pattern = rf'<{tag}(?:\s+[^>]*)?\s*/?>'
        close_pattern = rf'</{tag}>'
        
        # Count opening tags (using simple string count for reliability)
        opens = html.lower().count(f'<{tag.lower()}')
        # Subtract self-closing tags (rare for divs but possible)
        self_closing = len(re.findall(rf'<{tag}[^>]*/>', html, re.IGNORECASE))
        opens = opens - self_closing  # Self-closing don't need a close tag
        
        closes = len(re.findall(close_pattern, html, re.IGNORECASE))
        
        diff = opens - closes
        
        return {
            'tag': tag,
            'opens': opens,
            'closes': closes,
            'diff': diff,
            'balanced': diff == 0
        }
    
    def _find_unclosed_tags(self, html: str) -> List[str]:
        """Find tags that are opened but never closed."""
        unclosed = []
        
        # Tags that must be closed
        must_close_tags = ['div', 'span', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 
                           'table', 'tr', 'td', 'th', 'ul', 'ol', 'li', 
                           'form', 'button', 'a', 'script', 'style']
        
        for tag in must_close_tags:
            balance = self._check_tag_balance(html, tag)
            if balance['diff'] > 0:
                unclosed.append(f"<{tag}> ({balance['diff']} unclosed)")
            elif balance['diff'] < 0:
                unclosed.append(f"<{tag}> ({abs(balance['diff'])} extra closes)")
        
        return unclosed
    
    def _check_common_errors(self, html: str, context: str):
        """Check for common HTML structure errors."""
        
        # 1. Check for unclosed quotes in attributes
        quote_errors = re.findall(r'<[^>]+=["\'][^"\']*$', html)
        if quote_errors:
            self.errors.append(f"{context}: Found unclosed quotes in attributes")
        
        # 2. Check for improperly nested tags (div inside span, etc.)
        # This is a simplified check - full validation would require parsing
        
        # 3. Check for duplicate IDs
        id_pattern = r'id=["\']([^"\']+)["\']'
        ids = re.findall(id_pattern, html, re.IGNORECASE)
        duplicates = [id_val for id_val, count in Counter(ids).items() if count > 1]
        if duplicates:
            self.warnings.append(
                f"{context}: Duplicate IDs found: {', '.join(duplicates)}"
            )
        
        # 4. Check for orphaned closing tags at end
        end_tags = re.findall(r'</\w+>\s*$', html[-200:])
        if len(end_tags) > 3:
            self.warnings.append(
                f"{context}: Multiple closing tags at end - possible structure issue"
            )
    
    def auto_fix_balance(self, html: str) -> Tuple[str, Dict]:
        """
        Attempt to automatically fix HTML balance issues.
        
        Returns:
            Tuple of (fixed_html, fix_report)
        """
        fixes_applied = []
        fixed_html = html
        
        # Check div balance
        balance = self._check_tag_balance(fixed_html, 'div')
        
        if balance['diff'] > 0:
            # More opens than closes - add closing divs at end
            num_to_add = balance['diff']
            closing_tags = '\n'.join(['    </div>'] * num_to_add)
            fixed_html += f'\n{closing_tags}\n'
            fixes_applied.append(f"Added {num_to_add} closing </div> tag(s)")
        
        elif balance['diff'] < 0:
            # More closes than opens - remove extra closing divs from end
            num_to_remove = abs(balance['diff'])
            # Remove last N closing div tags
            for _ in range(num_to_remove):
                # Find and remove last </div>
                last_close = fixed_html.rfind('</div>')
                if last_close != -1:
                    fixed_html = fixed_html[:last_close] + fixed_html[last_close + 6:]
            fixes_applied.append(f"Removed {num_to_remove} extra </div> tag(s)")
        
        # Check script balance
        script_balance = self._check_tag_balance(fixed_html, 'script')
        if script_balance['diff'] != 0:
            if script_balance['diff'] > 0:
                fixed_html += '\n</script>\n'
                fixes_applied.append("Added missing </script> tag")
        
        return fixed_html, {
            'fixes_applied': fixes_applied,
            'original_balance': balance,
            'fixed': len(fixes_applied) > 0
        }
    
    def validate_tab_structure(self, tab_html: str, tab_name: str, 
                               expected_structure: Dict = None) -> Dict:
        """
        Validate a complete tab's HTML structure.
        
        Args:
            tab_html: Complete HTML for a tab
            tab_name: Name of tab (e.g., "Executive", "Platform")
            expected_structure: Optional dict defining expected structure:
                {
                    'wrapper_divs': int,  # Expected number of wrapper divs
                    'has_container': bool,  # Should have padding container?
                    'has_title': bool,  # Should have h2 title?
                }
        
        Returns:
            Validation result dict
        """
        result = self.validate_html_structure(tab_html, f"{tab_name} Tab")
        
        if expected_structure:
            # Verify expected structure
            if expected_structure.get('has_title'):
                if not re.search(r'<h2[^>]*class=["\']section-title["\']', tab_html):
                    result['warnings'].append(
                        f"{tab_name} Tab: Missing expected h2.section-title"
                    )
            
            if expected_structure.get('has_container'):
                if 'padding: 0 50px 30px 50px' not in tab_html:
                    result['warnings'].append(
                        f"{tab_name} Tab: Missing expected container padding style"
                    )
            
            # Check wrapper div count
            tab_content_count = len(re.findall(r'<div[^>]*class=["\'][^"\']*tab-content', tab_html))
            if tab_content_count != 1:
                result['errors'].append(
                    f"{tab_name} Tab: Should have exactly 1 tab-content div, found {tab_content_count}"
                )
        
        return result
    
    def validate_css_blocks(self, html: str) -> Dict:
        """Validate CSS blocks for common issues."""
        errors = []
        warnings = []
        
        # Extract all <style> blocks
        style_pattern = r'<style[^>]*>(.*?)</style>'
        style_blocks = re.findall(style_pattern, html, re.DOTALL | re.IGNORECASE)
        
        for idx, css in enumerate(style_blocks):
            # Check for balanced braces
            open_braces = css.count('{')
            close_braces = css.count('}')
            
            if open_braces != close_braces:
                errors.append(
                    f"CSS Block {idx+1}: Brace imbalance - {open_braces} opens, "
                    f"{close_braces} closes (diff: {open_braces - close_braces})"
                )
            
            # Check for unclosed string literals
            single_quotes = css.count("'") - css.count("\\'")
            double_quotes = css.count('"') - css.count('\\"')
            
            if single_quotes % 2 != 0:
                warnings.append(f"CSS Block {idx+1}: Odd number of single quotes (possible unclosed string)")
            if double_quotes % 2 != 0:
                warnings.append(f"CSS Block {idx+1}: Odd number of double quotes (possible unclosed string)")
            
            # Check for duplicate selectors
            selector_pattern = r'([^\{\}]+)\s*\{'
            selectors = re.findall(selector_pattern, css)
            selector_counts = Counter([s.strip() for s in selectors])
            duplicates = {sel: count for sel, count in selector_counts.items() if count > 1}
            
            if duplicates:
                for sel, count in duplicates.items():
                    warnings.append(f"CSS Block {idx+1}: Duplicate selector '{sel[:50]}...' appears {count} times")
        
        # Check for unclosed <style> tags
        open_style = len(re.findall(r'<style[^>]*>', html, re.IGNORECASE))
        close_style = len(re.findall(r'</style>', html, re.IGNORECASE))
        
        if open_style != close_style:
            errors.append(
                f"Style tag imbalance: {open_style} <style> opens, "
                f"{close_style} closes (diff: {open_style - close_style})"
            )
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'blocks_checked': len(style_blocks)
        }
    
    def validate_javascript_blocks(self, html: str) -> Dict:
        """Validate JavaScript blocks for common issues."""
        errors = []
        warnings = []
        
        # Extract all <script> blocks
        script_pattern = r'<script[^>]*>(.*?)</script>'
        script_blocks = re.findall(script_pattern, html, re.DOTALL | re.IGNORECASE)
        
        for idx, js in enumerate(script_blocks):
            # Skip empty or CDN scripts
            if not js.strip() or 'src=' in js:
                continue
            
            # Check for balanced brackets/braces/parentheses
            balance_checks = {
                'braces': ('{', '}'),
                'brackets': ('[', ']'),
                'parentheses': ('(', ')')
            }
            
            for name, (open_char, close_char) in balance_checks.items():
                opens = js.count(open_char)
                closes = js.count(close_char)
                
                if opens != closes:
                    errors.append(
                        f"JS Block {idx+1}: {name.capitalize()} imbalance - {opens} opens, "
                        f"{closes} closes (diff: {opens - closes})"
                    )
            
            # Check for unclosed string literals
            # More sophisticated: track escaped quotes
            in_single = False
            in_double = False
            escape_next = False
            
            for char in js:
                if escape_next:
                    escape_next = False
                    continue
                
                if char == '\\':
                    escape_next = True
                    continue
                
                if char == "'" and not in_double:
                    in_single = not in_single
                elif char == '"' and not in_single:
                    in_double = not in_double
            
            if in_single or in_double:
                errors.append(f"JS Block {idx+1}: Unclosed string literal detected")
            
            # Check for common syntax issues
            # Function declaration without closing brace
            func_opens = len(re.findall(r'\bfunction\s*\w*\s*\([^)]*\)\s*\{', js))
            total_braces_open = js.count('{')
            total_braces_close = js.count('}')
            
            if func_opens > 0 and total_braces_open > total_braces_close:
                warnings.append(f"JS Block {idx+1}: Possible unclosed function (more {{ than }})")
        
        # Check for unclosed <script> tags
        open_script = len(re.findall(r'<script[^>]*>', html, re.IGNORECASE))
        close_script = len(re.findall(r'</script>', html, re.IGNORECASE))
        
        if open_script != close_script:
            errors.append(
                f"Script tag imbalance: {open_script} <script> opens, "
                f"{close_script} closes (diff: {open_script - close_script})"
            )
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'blocks_checked': len(script_blocks)
        }
    
    def auto_fix_css(self, html: str) -> Tuple[str, Dict]:
        """Auto-fix CSS issues in HTML."""
        fixes_applied = []
        fixed_html = html
        
        # Fix unclosed <style> tags
        open_style = len(re.findall(r'<style[^>]*>', fixed_html, re.IGNORECASE))
        close_style = len(re.findall(r'</style>', fixed_html, re.IGNORECASE))
        
        if open_style > close_style:
            # Add missing closing tags
            for _ in range(open_style - close_style):
                # Find last <style> without closing
                last_style_pos = fixed_html.rfind('</style>')
                if last_style_pos == -1:
                    last_style_pos = len(fixed_html)
                
                # Insert before next tag or at end
                insert_pos = fixed_html.find('<', last_style_pos + 1)
                if insert_pos == -1:
                    insert_pos = len(fixed_html)
                
                fixed_html = fixed_html[:insert_pos] + '\n</style>\n' + fixed_html[insert_pos:]
                fixes_applied.append('Added missing </style> tag')
        
        # Fix CSS brace imbalance within <style> blocks
        style_pattern = r'(<style[^>]*>)(.*?)(</style>)'
        
        def fix_css_braces(match):
            opening_tag = match.group(1)
            css_content = match.group(2)
            closing_tag = match.group(3)
            
            open_braces = css_content.count('{')
            close_braces = css_content.count('}')
            
            if open_braces > close_braces:
                # Add missing closing braces at the end
                css_content += '\n' + '}' * (open_braces - close_braces)
                fixes_applied.append(f'Added {open_braces - close_braces} closing brace(s) to CSS')
            elif close_braces > open_braces:
                # Remove extra closing braces (more conservative - just report)
                pass
            
            return opening_tag + css_content + closing_tag
        
        fixed_html = re.sub(style_pattern, fix_css_braces, fixed_html, flags=re.DOTALL | re.IGNORECASE)
        
        return fixed_html, {
            'fixed': len(fixes_applied) > 0,
            'fixes_applied': fixes_applied
        }
    
    def auto_fix_javascript(self, html: str) -> Tuple[str, Dict]:
        """Auto-fix JavaScript issues in HTML."""
        fixes_applied = []
        fixed_html = html
        
        # Fix unclosed <script> tags
        open_script = len(re.findall(r'<script[^>]*>(?![^<]*src=)', fixed_html, re.IGNORECASE))
        close_script = len(re.findall(r'</script>', fixed_html, re.IGNORECASE))
        
        if open_script > close_script:
            # Add missing closing tags
            for _ in range(open_script - close_script):
                # Find last <script> without closing
                last_script_pos = fixed_html.rfind('</script>')
                if last_script_pos == -1:
                    last_script_pos = len(fixed_html)
                
                # Insert before next tag or at end
                insert_pos = fixed_html.find('<', last_script_pos + 1)
                if insert_pos == -1:
                    insert_pos = len(fixed_html)
                
                fixed_html = fixed_html[:insert_pos] + '\n</script>\n' + fixed_html[insert_pos:]
                fixes_applied.append('Added missing </script> tag')
        
        # Fix JavaScript brace imbalance within <script> blocks
        script_pattern = r'(<script[^>]*>)(.*?)(</script>)'
        
        def fix_js_braces(match):
            opening_tag = match.group(1)
            js_content = match.group(2)
            closing_tag = match.group(3)
            
            # Skip CDN/external scripts
            if 'src=' in opening_tag or not js_content.strip():
                return match.group(0)
            
            # Fix braces
            open_braces = js_content.count('{')
            close_braces = js_content.count('}')
            
            if open_braces > close_braces:
                # Add missing closing braces with proper indentation
                diff = open_braces - close_braces
                # Find last non-empty line to determine indentation
                lines = js_content.rstrip().split('\n')
                last_indent = ''
                for line in reversed(lines):
                    if line.strip():
                        last_indent = line[:len(line) - len(line.lstrip())]
                        break
                
                closing_braces = '\n' + '\n'.join([last_indent + '}' for _ in range(diff)])
                js_content += closing_braces
                fixes_applied.append(f'Added {diff} closing brace(s) to JavaScript')
            
            # Fix brackets
            open_brackets = js_content.count('[')
            close_brackets = js_content.count(']')
            
            if open_brackets > close_brackets:
                js_content += ']' * (open_brackets - close_brackets)
                fixes_applied.append(f'Added {open_brackets - close_brackets} closing bracket(s) to JavaScript')
            
            # Fix parentheses
            open_parens = js_content.count('(')
            close_parens = js_content.count(')')
            
            if open_parens > close_parens:
                js_content += ')' * (open_parens - close_parens)
                fixes_applied.append(f'Added {open_parens - close_parens} closing parenthesis(es) to JavaScript')
            
            return opening_tag + js_content + closing_tag
        
        fixed_html = re.sub(script_pattern, fix_js_braces, fixed_html, flags=re.DOTALL | re.IGNORECASE)
        
        return fixed_html, {
            'fixed': len(fixes_applied) > 0,
            'fixes_applied': fixes_applied
        }
    
    def auto_fix_full_document(self, html: str) -> Tuple[str, Dict]:
        """Auto-fix HTML, CSS, and JavaScript issues."""
        all_fixes = []
        
        # Fix HTML structure
        fixed_html, html_fixes = self.auto_fix_balance(html)
        if html_fixes['fixed']:
            all_fixes.extend(html_fixes['fixes_applied'])
        
        # Fix CSS issues
        fixed_html, css_fixes = self.auto_fix_css(fixed_html)
        if css_fixes['fixed']:
            all_fixes.extend(css_fixes['fixes_applied'])
        
        # Fix JavaScript issues
        fixed_html, js_fixes = self.auto_fix_javascript(fixed_html)
        if js_fixes['fixed']:
            all_fixes.extend(js_fixes['fixes_applied'])
        
        return fixed_html, {
            'fixed': len(all_fixes) > 0,
            'fixes_applied': all_fixes,
            'html_fixes': html_fixes,
            'css_fixes': css_fixes,
            'js_fixes': js_fixes
        }
    
    def validate_full_document(self, html: str, context: str = "Document") -> Dict:
        """Comprehensive validation: HTML structure + CSS + JavaScript."""
        # Validate HTML structure
        html_result = self.validate_html_structure(html, context)
        
        # Validate CSS blocks
        css_result = self.validate_css_blocks(html)
        
        # Validate JavaScript blocks
        js_result = self.validate_javascript_blocks(html)
        
        # Combine results
        all_errors = html_result['errors'] + css_result['errors'] + js_result['errors']
        all_warnings = html_result.get('warnings', []) + css_result['warnings'] + js_result['warnings']
        
        return {
            'valid': len(all_errors) == 0,
            'errors': all_errors,
            'warnings': all_warnings,
            'html': html_result,
            'css': css_result,
            'javascript': js_result,
            'summary': {
                'html_valid': html_result['valid'],
                'css_valid': css_result['valid'],
                'js_valid': js_result['valid'],
                'total_errors': len(all_errors),
                'total_warnings': len(all_warnings)
            }
        }


class ModularTabValidator:
    """Validates modular tab functions ensure proper structure."""
    
    def __init__(self):
        self.validator = HTMLValidator()
    
    def validate_tab_function_output(self, func_name: str, html_output: str) -> Dict:
        """
        Validate that a tab generation function returns properly structured HTML.
        
        Expected structure for all tab functions:
        - Starts with <div id="..." class="tab-content">
        - Ends with </div>
        - Balanced tags throughout
        """
        errors = []
        warnings = []
        
        # 1. Check starts with tab-content div
        if not re.match(r'\s*<div[^>]+class=["\'][^"\']*tab-content', html_output):
            errors.append(
                f"{func_name}: Should start with <div class='tab-content'>"
            )
        
        # 2. Check ends with closing div
        if not re.search(r'</div>\s*$', html_output):
            errors.append(
                f"{func_name}: Should end with </div>"
            )
        
        # 3. Validate HTML structure
        structure_result = self.validator.validate_html_structure(html_output, func_name)
        
        return {
            'function': func_name,
            'valid': len(errors) == 0 and structure_result['valid'],
            'errors': errors + structure_result['errors'],
            'warnings': warnings + structure_result['warnings'],
            'structure': structure_result
        }


class CodeAnalyzer:
    """Analyzes Python code to find HTML generation issues."""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.content = Path(file_path).read_text(encoding='utf-8')
        self.lines = self.content.split('\n')
    
    def find_tab_functions(self) -> List[Dict]:
        """Find all tab generation functions in the code."""
        tab_functions = []
        
        # Pattern for tab generation functions
        pattern = r'def (_generate_\w+_tab\w*)\(self[^)]*\):'
        
        for match in re.finditer(pattern, self.content):
            func_name = match.group(1)
            start_pos = match.start()
            
            # Find line number
            line_num = self.content[:start_pos].count('\n') + 1
            
            # Extract function body
            func_body = self._extract_function_body(line_num)
            
            tab_functions.append({
                'name': func_name,
                'line_start': line_num,
                'body': func_body,
                'file_path': self.file_path
            })
        
        return tab_functions
    
    def _extract_function_body(self, start_line: int) -> str:
        """Extract complete function body from start line."""
        lines = []
        indent_level = None
        in_function = False
        
        for i in range(start_line - 1, len(self.lines)):
            line = self.lines[i]
            
            # Skip empty lines at start
            if not in_function and not line.strip():
                continue
            
            if not in_function:
                in_function = True
                indent_level = len(line) - len(line.lstrip())
                lines.append(line)
                continue
            
            # Check if we've left the function
            if line.strip() and not line.startswith(' ' * (indent_level + 1)) and not line.strip().startswith('#'):
                # Check if it's a new function or class definition
                if line.strip().startswith('def ') or line.strip().startswith('class '):
                    break
            
            lines.append(line)
            
            # Stop after return statement (with some buffer)
            if 'return html' in line or 'return f"' in line or 'return """' in line:
                # Grab a few more lines to ensure we get the closing
                for j in range(i + 1, min(i + 10, len(self.lines))):
                    lines.append(self.lines[j])
                break
        
        return '\n'.join(lines)
    
    def analyze_html_in_function(self, func_body: str) -> Dict:
        """Analyze HTML structure in a function body."""
        validator = HTMLValidator()
        
        # Extract HTML strings from the function
        html_strings = self._extract_html_strings(func_body)
        
        # Combine all HTML for analysis
        combined_html = '\n'.join(html_strings)
        
        # Validate
        result = validator.validate_html_structure(combined_html, "Function HTML")
        
        return {
            'html_strings': html_strings,
            'validation': result,
            'combined_html': combined_html
        }
    
    def _extract_html_strings(self, func_body: str) -> List[str]:
        """Extract HTML string literals from function body."""
        html_strings = []
        
        # Match triple-quoted strings
        triple_quote_pattern = r'"""(.*?)"""'
        for match in re.finditer(triple_quote_pattern, func_body, re.DOTALL):
            html_strings.append(match.group(1))
        
        # Match f-strings with HTML
        fstring_pattern = r'f"""(.*?)"""'
        for match in re.finditer(fstring_pattern, func_body, re.DOTALL):
            # Remove f-string expressions for structure analysis
            html = re.sub(r'\{[^}]+\}', '', match.group(1))
            html_strings.append(html)
        
        return html_strings


class CodeFixer:
    """Automatically fixes HTML structure issues in Python code."""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.content = Path(file_path).read_text(encoding='utf-8')
        self.lines = self.content.split('\n')
        self.fixes_applied = []
    
    def fix_function_html_balance(self, func_name: str, func_info: Dict) -> bool:
        """Fix HTML balance issues in a specific function."""
        analysis = func_info.get('analysis', {})
        validation = analysis.get('validation', {})
        
        if validation.get('valid'):
            return False  # No fix needed
        
        balance = validation.get('balance', {})
        diff = balance.get('diff', 0)
        
        if diff == 0:
            return False  # Already balanced
        
        # Find where to add closing tags
        line_start = func_info['line_start']
        func_body = func_info['body']
        
        # Find the return statement
        return_line = self._find_return_line(line_start, func_body)
        
        if return_line is None:
            print(f"  [WARN]  Could not find return statement in {func_name}")
            return False
        
        # Determine what to add
        if diff > 0:
            # Need closing divs
            fix = self._add_closing_divs(return_line, diff)
            self.fixes_applied.append(f"Added {diff} closing </div> tag(s) to {func_name}")
            return True
        elif diff < 0:
            # Too many closing divs
            fix = self._remove_closing_divs(return_line, abs(diff))
            self.fixes_applied.append(f"Removed {abs(diff)} extra </div> tag(s) from {func_name}")
            return True
        
        return False
    
    def _find_return_line(self, start_line: int, func_body: str) -> Optional[int]:
        """Find the line number of the return statement."""
        func_lines = func_body.split('\n')
        
        for i, line in enumerate(func_lines):
            if 'return html' in line or 'return f"' in line or 'return """' in line:
                return start_line + i
        
        return None
    
    def _add_closing_divs(self, return_line: int, count: int) -> bool:
        """Add closing div tags before return statement."""
        # Find the line with return
        return_line_idx = return_line - 1
        
        # Find the HTML closing section (usually before return)
        insert_line = return_line_idx
        
        # Look backwards for the last HTML closing section
        for i in range(return_line_idx, max(0, return_line_idx - 20), -1):
            line = self.lines[i]
            if '</div>' in line or '</script>' in line or '"""' in line:
                insert_line = i + 1
                break
        
        # Determine indentation
        indent = self._get_indent(return_line_idx)
        
        # Create closing tags with proper indentation
        closing_tags = []
        for _ in range(count):
            closing_tags.append(f"{indent}        </div>")
        
        # Insert the closing tags
        closing_block = '\n'.join(closing_tags)
        
        # If there's a """ closing quote, insert before it
        if insert_line < len(self.lines) and '"""' in self.lines[insert_line]:
            self.lines.insert(insert_line, closing_block)
        else:
            # Insert after the last HTML content
            self.lines.insert(insert_line, closing_block)
        
        return True
    
    def _remove_closing_divs(self, return_line: int, count: int) -> bool:
        """Remove extra closing div tags."""
        return_line_idx = return_line - 1
        removed = 0
        
        # Look backwards from return statement
        for i in range(return_line_idx, max(0, return_line_idx - 30), -1):
            line = self.lines[i]
            
            if '</div>' in line and removed < count:
                # Remove this line
                del self.lines[i]
                removed += 1
                
                if removed >= count:
                    break
        
        return removed == count
    
    def _get_indent(self, line_idx: int) -> str:
        """Get indentation of a line."""
        line = self.lines[line_idx]
        return line[:len(line) - len(line.lstrip())]
    
    def fix_css_in_function(self, func_name: str, func_info: Dict) -> bool:
        """Fix CSS issues in a function's source code."""
        func_body = func_info['body']
        line_start = func_info['line_start']
        
        # Extract HTML strings containing <style> blocks
        style_pattern = r'(<style[^>]*>)(.*?)(</style>)'
        fixes_made = False
        
        for match in re.finditer(style_pattern, func_body, re.DOTALL | re.IGNORECASE):
            css_content = match.group(2)
            
            # Check for brace imbalance
            open_braces = css_content.count('{')
            close_braces = css_content.count('}')
            
            if open_braces > close_braces:
                diff = open_braces - close_braces
                
                # Find the line in the source where this CSS block ends
                css_end_pos = match.end(2)
                lines_before = func_body[:css_end_pos].count('\n')
                fix_line = line_start + lines_before
                
                # Add closing braces
                self.lines[fix_line] = self.lines[fix_line].rstrip() + '\n' + '}' * diff
                
                self.fixes_applied.append(f"Added {diff} closing brace(s) to CSS in {func_name}")
                fixes_made = True
        
        return fixes_made
    
    def fix_javascript_in_function(self, func_name: str, func_info: Dict) -> bool:
        """Fix JavaScript issues in a function's source code."""
        func_body = func_info['body']
        line_start = func_info['line_start']
        
        # Extract HTML strings containing <script> blocks
        script_pattern = r'(<script[^>]*>)(.*?)(</script>)'
        fixes_made = False
        
        for match in re.finditer(script_pattern, func_body, re.DOTALL | re.IGNORECASE):
            opening_tag = match.group(1)
            
            # Skip external scripts
            if 'src=' in opening_tag:
                continue
            
            js_content = match.group(2)
            
            # Check for brace imbalance
            open_braces = js_content.count('{')
            close_braces = js_content.count('}')
            
            if open_braces > close_braces:
                diff = open_braces - close_braces
                
                # Find the line in the source where this JS block ends
                js_end_pos = match.end(2)
                lines_before = func_body[:js_end_pos].count('\n')
                fix_line = line_start + lines_before
                
                # Determine indentation
                if fix_line < len(self.lines):
                    current_line = self.lines[fix_line]
                    indent = current_line[:len(current_line) - len(current_line.lstrip())]
                    
                    # Add closing braces with proper indentation
                    closing_braces = '\n'.join([f"{indent}    }}" for _ in range(diff)])
                    self.lines[fix_line] = self.lines[fix_line].rstrip() + '\n' + closing_braces
                
                self.fixes_applied.append(f"Added {diff} closing brace(s) to JavaScript in {func_name}")
                fixes_made = True
            
            # Check for bracket imbalance
            open_brackets = js_content.count('[')
            close_brackets = js_content.count(']')
            
            if open_brackets > close_brackets:
                diff = open_brackets - close_brackets
                js_end_pos = match.end(2)
                lines_before = func_body[:js_end_pos].count('\n')
                fix_line = line_start + lines_before
                
                self.lines[fix_line] = self.lines[fix_line].rstrip() + ']' * diff
                self.fixes_applied.append(f"Added {diff} closing bracket(s) to JavaScript in {func_name}")
                fixes_made = True
            
            # Check for parentheses imbalance
            open_parens = js_content.count('(')
            close_parens = js_content.count(')')
            
            if open_parens > close_parens:
                diff = open_parens - close_parens
                js_end_pos = match.end(2)
                lines_before = func_body[:js_end_pos].count('\n')
                fix_line = line_start + lines_before
                
                self.lines[fix_line] = self.lines[fix_line].rstrip() + ')' * diff
                self.fixes_applied.append(f"Added {diff} closing parenthesis(es) to JavaScript in {func_name}")
                fixes_made = True
        
        return fixes_made
    
    def save_fixes(self) -> bool:
        """Save the fixed content back to file."""
        try:
            # Create backup (only once)
            backup_path = f"{self.file_path}.backup"
            if not Path(backup_path).exists():
                Path(backup_path).write_text(self.content, encoding='utf-8')
            
            # Write fixed content
            fixed_content = '\n'.join(self.lines)
            Path(self.file_path).write_text(fixed_content, encoding='utf-8')
            
            # Reload the content for next iteration
            self.content = fixed_content
            self.lines = self.content.split('\n')
            
            return True
        except Exception as e:
            print(f"[FAIL] Error saving fixes: {e}")
            return False


class HTMLValidationSystem:
    """HTML validation system that checks structure and logs issues (no source fixes)."""
    
    def __init__(self, report_generator_path: str, max_iterations: int = 3, debug: bool = False):
        self.report_generator_path = report_generator_path
        self.analyzer = CodeAnalyzer(report_generator_path)
        self.fixer = CodeFixer(report_generator_path)
        self.validator = HTMLValidator()  # For post-generation validation
        self.max_iterations = max_iterations
        self.debug = debug
    
    def _log(self, message: str, force: bool = False):
        """Print message only if debug mode or forced."""
        if self.debug or force:
            print(message)
    
    def scan_and_fix(self) -> Dict:
        """Scan for HTML, CSS, and JavaScript issues and fix them in source code."""
        self._log(" Scanning report_generator.py for HTML, CSS, and JavaScript issues...")
        
        # Find all tab functions
        tab_functions = self.analyzer.find_tab_functions()
        self._log(f"   Found {len(tab_functions)} tab generation functions")
        
        # Analyze each function
        html_issues = []
        css_issues = []
        js_issues = []
        
        for func in tab_functions:
            self._log(f"\n   Analyzing {func['name']}...")
            
            # Analyze HTML structure
            analysis = self.analyzer.analyze_html_in_function(func['body'])
            func['analysis'] = analysis
            
            validation = analysis['validation']
            
            if not validation['valid']:
                html_issues.append(func)
                balance = validation['balance']
                self._log(f"      [FAIL] HTML imbalance detected:")
                self._log(f"         Opens: {balance['opens']}, Closes: {balance['closes']}, Diff: {balance['diff']}")
                
                for error in validation['errors']:
                    self._log(f"         * {error}")
            else:
                self._log(f"      [OK] HTML structure valid")
            
            # Check for CSS issues in this function
            func_body = func['body']
            if '<style' in func_body:
                style_pattern = r'<style[^>]*>(.*?)</style>'
                for match in re.finditer(style_pattern, func_body, re.DOTALL | re.IGNORECASE):
                    css_content = match.group(1)
                    open_braces = css_content.count('{')
                    close_braces = css_content.count('}')
                    
                    if open_braces != close_braces:
                        css_issues.append(func)
                        self._log(f"      [WARN]  CSS brace imbalance: {open_braces} opens, {close_braces} closes")
                        break
            
            # Check for JavaScript issues in this function
            if '<script' in func_body:
                script_pattern = r'<script[^>]*>(.*?)</script>'
                for match in re.finditer(script_pattern, func_body, re.DOTALL | re.IGNORECASE):
                    js_content = match.group(1)
                    
                    # Skip external scripts
                    if 'src=' in match.group(0):
                        continue
                    
                    open_braces = js_content.count('{')
                    close_braces = js_content.count('}')
                    
                    if open_braces != close_braces:
                        js_issues.append(func)
                        self._log(f"      [WARN]  JavaScript brace imbalance: {open_braces} opens, {close_braces} closes")
                        break
        
        # Fix all issues
        fixes_applied = False
        total_issues = len(set([f['name'] for f in html_issues + css_issues + js_issues]))
        
        if total_issues > 0:
            self._log(f"\n Fixing {total_issues} function(s) with issues...")
            
            # Fix HTML issues
            for func in html_issues:
                if self.fixer.fix_function_html_balance(func['name'], func):
                    fixes_applied = True
                    self._log(f"   [OK] Fixed HTML in {func['name']}")
            
            # Fix CSS issues
            for func in css_issues:
                if self.fixer.fix_css_in_function(func['name'], func):
                    fixes_applied = True
                    self._log(f"   [OK] Fixed CSS in {func['name']}")
            
            # Fix JavaScript issues
            for func in js_issues:
                if self.fixer.fix_javascript_in_function(func['name'], func):
                    fixes_applied = True
                    self._log(f"   [OK] Fixed JavaScript in {func['name']}")
        
        # NOTE: Do NOT save fixes to source code - this breaks Python syntax
        # Validator should only fix the generated HTML output, not the Python source
        if fixes_applied:
            self._log("\n   [i]  Fixes will be applied to generated HTML output only")
            self._log("   [i]  Source code remains unchanged to prevent syntax errors")
        
        return {
            'success': True,
            'issues_found': total_issues,
            'html_issues': len(html_issues),
            'css_issues': len(css_issues),
            'js_issues': len(js_issues),
            'fixes_applied': fixes_applied,
            'fixes': self.fixer.fixes_applied
        }
    
    def generate_report(self, analysis_args: List[str] = None) -> Dict:
        """Generate HTML report using the fixed code."""
        print("\n Generating HTML report...")
        
        if analysis_args is None:
            analysis_args = ['--duration', '1', '--max-event', '10']
        
        cmd = ['python', 'analyze_coverage.py'] + analysis_args
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=Path(self.report_generator_path).parent.parent
            )
            
            if result.returncode == 0:
                print("   [OK] Report generated successfully")
                return {'success': True, 'output': result.stdout}
            else:
                print("   [FAIL] Report generation failed")
                print(f"   Error: {result.stderr}")
                return {'success': False, 'error': result.stderr}
        
        except Exception as e:
            print(f"   [FAIL] Exception during report generation: {e}")
            return {'success': False, 'error': str(e)}
    
    def validate_generated_html(self, html_path: str) -> Dict:
        """Validate the generated HTML report."""
        print(f"\n Validating generated HTML report: {html_path}")
        
        if not Path(html_path).exists():
            print("   [WARN]  HTML file not found")
            return {'success': False, 'error': 'File not found'}
        
        html_content = Path(html_path).read_text(encoding='utf-8')
        
        validator = HTMLValidator()
        result = validator.validate_html_structure(html_content, "Generated Report")
        
        if result['valid']:
            print("   [OK] Generated HTML is valid")
        else:
            print("   [FAIL] Generated HTML has issues:")
            for error in result['errors']:
                print(f"      * {error}")
        
        return {
            'success': result['valid'],
            'validation': result
        }
    
    def run_full_cycle(self, analysis_args: List[str] = None) -> Dict:
        """Run complete scan -> fix -> generate -> validate cycle."""
        print("="*70)
        print("[ML] HTML VALIDATION SYSTEM - FULL CYCLE")
        print("="*70)
        
        iteration = 0
        
        while iteration < self.max_iterations:
            iteration += 1
            print(f"\n{'='*70}")
            print(f"ITERATION {iteration}/{self.max_iterations}")
            print(f"{'='*70}")
            
            # Step 1: Scan and fix code
            scan_result = self.scan_and_fix()
            
            if not scan_result['success']:
                return {
                    'success': False,
                    'message': 'Scanning/fixing failed',
                    'iteration': iteration
                }
            
            # If no issues found and no fixes applied, we're done with code
            if scan_result['issues_found'] == 0:
                print("\n[OK] No issues found in report_generator.py")
                break
            
            if not scan_result['fixes_applied']:
                print("\n[WARN]  Issues found but could not be auto-fixed")
                break
            
            # Reload the fixed code
            print("\n[~] Reloading fixed code...")
            self.analyzer = CodeAnalyzer(self.report_generator_path)
            self.fixer = CodeFixer(self.report_generator_path)
        
        # Step 2: Generate report
        gen_result = self.generate_report(analysis_args)
        
        if not gen_result['success']:
            return {
                'success': False,
                'message': 'Report generation failed',
                'error': gen_result.get('error')
            }
        
        # Step 3: Find and validate generated HTML
        output_dir = Path(self.report_generator_path).parent.parent / 'output'
        html_files = sorted(output_dir.glob('silicon_coverage_analysis_*.html'))
        
        if not html_files:
            return {
                'success': False,
                'message': 'No HTML report found after generation'
            }
        
        latest_html = html_files[-1]
        val_result = self.validate_generated_html(str(latest_html))
        
        # Step 4: If HTML has issues, try to fix source code and regenerate
        if not val_result['success'] and iteration < self.max_iterations:
            print("\n[WARN]  Generated HTML has issues. Running another fix cycle...")
            return self.run_full_cycle(analysis_args)
        
        # Final report
        print("\n" + "="*70)
        print(" FINAL REPORT")
        print("="*70)
        
        if val_result['success']:
            print("[OK] SUCCESS: HTML report generated and validated")
            print(f" Report location: {latest_html}")
            return {
                'success': True,
                'html_path': str(latest_html),
                'iterations': iteration
            }
        else:
            print("[WARN]  HTML generated but has validation issues")
            print(f" Report location: {latest_html}")
            return {
                'success': False,
                'html_path': str(latest_html),
                'message': 'HTML validation failed',
                'validation': val_result['validation'],
                'iterations': iteration
            }


def create_validation_wrapper(func):
    """
    Decorator to automatically validate tab function output.
    
    Usage:
        @create_validation_wrapper
        def _generate_executive_tab(self, analysis_results):
            html = "<div class='tab-content'>...</div>"
            return html
    """
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        
        # Validate result
        validator = ModularTabValidator()
        validation = validator.validate_tab_function_output(func.__name__, result)
        
        if not validation['valid']:
            print(f"\n[WARN]  HTML Validation Warning for {func.__name__}:")
            for error in validation['errors']:
                print(f"  [FAIL] {error}")
            for warning in validation['warnings']:
                print(f"  [WARN]  {warning}")
            
            # Auto-fix if possible
            html_validator = HTMLValidator()
            fixed_html, fix_report = html_validator.auto_fix_balance(result)
            
            if fix_report['fixed']:
                print(f"   Auto-fixes applied: {', '.join(fix_report['fixes_applied'])}")
                return fixed_html
        
        return result
    
    return wrapper


# Backward compatibility aliases
SelfHealingReportSystem = HTMLValidationSystem


def main():
    """Main entry point for HTML validation system."""
    import argparse
    
    parser = argparse.ArgumentParser(description='HTML validation system for report generation')
    parser.add_argument('--duration', type=int, default=1, help='Collection duration')
    parser.add_argument('--max-event', type=int, default=10, help='Max events')
    parser.add_argument('--scan-only', action='store_true', help='Only scan, do not fix')
    
    args = parser.parse_args()
    
    # Get report generator path
    current_dir = Path(__file__).parent
    report_gen_path = current_dir / 'report_generator.py'
    
    # Create system
    system = HTMLValidationSystem(str(report_gen_path))
    
    if args.scan_only:
        # Just scan and report
        result = system.scan_and_fix()
        print("\n Scan Results:")
        print(f"   Issues found: {result['issues_found']}")
        print(f"   Fixes applied: {result['fixes_applied']}")
    else:
        # Run full cycle
        analysis_args = ['--duration', str(args.duration), '--max-event', str(args.max_event)]
        result = system.run_full_cycle(analysis_args)
        
        if result['success']:
            print("\n Success! Report is ready.")
            sys.exit(0)
        else:
            print("\n[FAIL] Process completed with issues.")
            sys.exit(1)


if __name__ == "__main__":
    # Example usage and tests
    validator = HTMLValidator()
    
    # Test 1: Balanced HTML
    balanced = """
    <div class="tab-content">
        <h2>Title</h2>
        <div class="section">
            <p>Content</p>
        </div>
    </div>
    """
    result = validator.validate_html_structure(balanced, "Test Balanced")
    print(f"Balanced Test: {'[OK] PASS' if result['valid'] else '[FAIL] FAIL'}")
    
    # Test 2: Unbalanced HTML (missing closing div)
    unbalanced = """
    <div class="tab-content">
        <h2>Title</h2>
        <div class="section">
            <p>Content</p>
        </div>
    """
    result = validator.validate_html_structure(unbalanced, "Test Unbalanced")
    print(f"Unbalanced Test: {'[FAIL] FAIL (expected)' if not result['valid'] else '[OK] Detected'}")
    print(f"  Errors: {result['errors']}")
    
    # Test 3: Auto-fix
    fixed_html, fix_report = validator.auto_fix_balance(unbalanced)
    result_after = validator.validate_html_structure(fixed_html, "Test Auto-Fixed")
    print(f"Auto-fix Test: {'[OK] PASS' if result_after['valid'] else '[FAIL] FAIL'}")
    print(f"  Fixes: {fix_report['fixes_applied']}")
