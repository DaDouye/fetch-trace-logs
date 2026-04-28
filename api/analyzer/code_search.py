#!/usr/bin/env python3
"""
Codebase search module - searches Java files for keywords
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional


class CodeSearch:
    """
    Search codebase for relevant code files based on keywords
    """

    # Search scope: only Java files under web/src/main/java
    SEARCH_SCOPE_PATTERN = re.compile(r'web/src/main/java[/\\].*\.java$')

    def __init__(self, repo_path: str):
        """
        Initialize code search

        :param repo_path: Path to the repository
        """
        self.repo_path = repo_path

    def search(
        self,
        api_paths: List[str] = None,
        class_names: List[str] = None,
        error_patterns: List[str] = None,
        business_terms: List[str] = None,
        max_results_per_keyword: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search codebase for files matching any of the keywords

        :param api_paths: List of API paths to search for
        :param class_names: List of class names to search for
        :param error_patterns: List of error patterns to search for
        :param business_terms: List of business terms to search for
        :param max_results_per_keyword: Maximum results per keyword
        :return: List of search results
        """
        results = []
        seen_files = set()

        keywords = []
        if api_paths:
            keywords.extend(api_paths)
        if class_names:
            keywords.extend(class_names)
        if error_patterns:
            keywords.extend(error_patterns)
        if business_terms:
            keywords.extend(business_terms)

        for keyword in keywords:
            keyword_results = self._search_keyword(
                keyword,
                max_results=max_results_per_keyword
            )

            for result in keyword_results:
                # Avoid duplicates
                file_path = result['file_path']
                if file_path not in seen_files:
                    seen_files.add(file_path)
                    results.append(result)

        return results

    def _search_keyword(self, keyword: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search for a single keyword in Java files

        :param keyword: Keyword to search for
        :param max_results: Maximum number of results
        :return: List of matching files with line numbers
        """
        results = []

        if not os.path.exists(self.repo_path):
            return results

        # Walk through Java files in the search scope
        for root, dirs, files in os.walk(self.repo_path):
            # Skip hidden directories and non-Java files
            dirs[:] = [d for d in dirs if not d.startswith('.')]

            for file in files:
                if not file.endswith('.java'):
                    continue

                file_path = os.path.join(root, file)

                # Apply search scope filter
                if not self.SEARCH_SCOPE_PATTERN.search(file_path):
                    continue

                # Search in file content
                matches = self._search_in_file(file_path, keyword)
                if matches:
                    results.append({
                        'file_path': file_path,
                        'keyword': keyword,
                        'matches': matches[:5]  # Limit matches per file
                    })

                    if len(results) >= max_results:
                        return results

        return results

    def _search_in_file(self, file_path: str, keyword: str) -> List[Dict[str, Any]]:
        """
        Search for keyword in a single file

        :param file_path: Path to the file
        :param keyword: Keyword to search for
        :return: List of matches with line numbers and content
        """
        matches = []

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    # Simple substring search (case-insensitive)
                    if keyword.lower() in line.lower():
                        # Get some context (previous and next lines)
                        matches.append({
                            'line_number': line_num,
                            'content': line.strip(),
                            'context': self._get_line_context(file_path, line_num)
                        })
        except Exception:
            pass

        return matches

    def _get_line_context(self, file_path: str, line_num: int, context_lines: int = 2) -> List[Dict]:
        """
        Get surrounding context lines

        :param file_path: Path to the file
        :param line_num: Target line number
        :param context_lines: Number of lines before/after to include
        :return: List of context lines with line numbers
        """
        context = []

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            start = max(0, line_num - context_lines - 1)
            end = min(len(lines), line_num + context_lines)

            for i in range(start, end):
                context.append({
                    'line_number': i + 1,
                    'content': lines[i].strip(),
                    'is_target': i + 1 == line_num
                })
        except Exception:
            pass

        return context

    def search_by_class_name(self, class_name: str) -> Optional[Dict[str, Any]]:
        """
        Search for a specific class in the codebase

        :param class_name: Name of the class to find
        :return: Dict with file path and class info, or None
        """
        # Build potential file paths
        potential_dirs = [
            'web/src/main/java'
        ]

        class_file_name = f"{class_name}.java"

        for base_dir in potential_dirs:
            search_dir = os.path.join(self.repo_path, base_dir)
            if not os.path.exists(search_dir):
                continue

            for root, dirs, files in os.walk(search_dir):
                if class_file_name in files:
                    file_path = os.path.join(root, class_file_name)
                    return self._parse_class_info(file_path, class_name)

        return None

    def _parse_class_info(self, file_path: str, class_name: str) -> Dict[str, Any]:
        """
        Parse basic class information from Java file

        :param file_path: Path to the Java file
        :param class_name: Name of the class
        :return: Dict with class information
        """
        info = {
            'file_path': file_path,
            'class_name': class_name,
            'package': None,
            'methods': [],
            'annotations': []
        }

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # Extract package
            package_match = re.search(r'package\s+([\w\.]+)\s*;', content)
            if package_match:
                info['package'] = package_match.group(1)

            # Extract class annotations
            annotation_pattern = r'@(\w+)(?:\([^)]*\))?'
            info['annotations'] = re.findall(annotation_pattern, content)

            # Extract public methods
            method_pattern = r'public\s+(?:static\s+)?(?:\w+(?:<[^>]+>)?\s+)+(\w+)\s*\([^)]*\)\s*(?:throws\s+[\w,\s]+)?\s*\{'
            info['methods'] = re.findall(method_pattern, content)

        except Exception:
            pass

        return info


def main():
    """Test code search"""
    import sys

    if len(sys.argv) < 3:
        print("Usage: python code_search.py <repo_path> <keyword>")
        sys.exit(1)

    repo_path = sys.argv[1]
    keyword = sys.argv[2]

    searcher = CodeSearch(repo_path)
    results = searcher.search([keyword])

    print(f"Search results for '{keyword}':")
    for result in results:
        print(f"\nFile: {result['file_path']}")
        print(f"Keyword: {result['keyword']}")
        for match in result['matches']:
            print(f"  Line {match['line_number']}: {match['content'][:80]}...")


if __name__ == "__main__":
    main()