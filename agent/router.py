import yaml
import json
import urllib.request
import re


class ToolRouter:
    """Routes user queries to relevant tool categories.

    Uses domain-based priority resolution: sub-categories in the same domain
    compete via priority (highest wins). Non-domain categories are additive.
    Falls back to LLM for ambiguous queries.
    """

    def __init__(self, rules_path: str = "rules.yaml", use_llm: bool = True, llm_model: str = "qwen3:1.7b"):
        with open(rules_path) as f:
            self.rules = yaml.safe_load(f)

        self.use_llm = use_llm
        self.llm_model = llm_model
        self.categories = self.rules.get("categories", {})
        self.fallback = self.rules.get("fallback", "all")

    def _keyword_match(self, query: str) -> list[dict]:
        """Match query against keywords. Returns all matches with metadata.

        Uses word-boundary matching to avoid substring false positives
        (e.g., "commit" should not match "commits").
        """
        query_lower = query.lower()
        matches = []

        for cat_name, cat_data in self.categories.items():
            for keyword in cat_data.get("keywords", []):
                # Word-boundary match: keyword must be a whole word
                pattern = r'\b' + re.escape(keyword) + r'\b'
                if re.search(pattern, query_lower):
                    matches.append({
                        "category": cat_name,
                        "domain": cat_data.get("domain"),
                        "priority": cat_data.get("priority", 0),
                    })
                    break

        return matches

    def _resolve_matches(self, matches: list[dict]) -> list[str]:
        """Resolve keyword matches: highest priority per domain wins.

        - Categories with a domain are grouped; highest priority per domain wins.
        - Categories without a domain are treated as unique (always included).
        """
        domain_best = {}  # domain -> {category, priority}
        standalone = []

        for m in matches:
            domain = m["domain"]
            if domain:
                if domain not in domain_best or m["priority"] > domain_best[domain]["priority"]:
                    domain_best[domain] = m
            else:
                standalone.append(m["category"])

        result = standalone + [m["category"] for m in domain_best.values()]
        return result

    def _llm_classify(self, query: str) -> list[str]:
        """Use small LLM to classify query into tool categories."""
        category_labels = {
            "git_ambiguous": "git/version control",
            "filesystem": "file operations",
            "web": "web search/fetch",
            "code": "code execution",
            "knowledge": "knowledge base",
        }
        cat_list = ", ".join(f'"{k}" ({v})' for k, v in category_labels.items())

        messages = [
            {"role": "system", "content": "Classify queries into tool categories. Reply with ONLY a JSON array."},
            {"role": "user", "content": f"Categories: {cat_list}\n\nQuery: {query}\n\nCategories:"},
        ]

        try:
            payload = json.dumps({
                "model": self.llm_model,
                "messages": messages,
                "stream": False,
                "think": False,
                "options": {
                    "temperature": 0,
                    "num_predict": 30,
                },
            }).encode("utf-8")

            req = urllib.request.Request(
                "http://localhost:11434/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
            )

            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            response_text = data.get("message", {}).get("content", "").strip()

            # Strip qwen3 thinking tags if present
            if "<think>" in response_text:
                import re
                response_text = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL).strip()

            # Parse JSON array from response
            start = response_text.find("[")
            end = response_text.rfind("]") + 1
            if start >= 0 and end > start:
                categories = json.loads(response_text[start:end])
                valid = [c for c in categories if c in self.categories]
                return valid

        except Exception as e:
            print(f"[router] LLM classification failed: {e}")

        return []

    def classify(self, query: str) -> list[str] | None:
        """Classify query into tool categories.

        Returns:
            List of category names, or None if no match (means "all tools").
        """
        # Step 1: keyword matching with domain priority resolution
        raw_matches = self._keyword_match(query)
        if raw_matches:
            resolved = self._resolve_matches(raw_matches)
            return resolved

        # Step 2: LLM fallback
        if self.use_llm:
            matches = self._llm_classify(query)
            if matches:
                return matches

        # Step 3: no match — return None (caller exposes all tools)
        return None

    def get_tools(self, query: str, all_tools: list) -> list:
        """Return filtered tool list for the worker model.

        Args:
            query: User's input text.
            all_tools: Complete list of all available tool functions.

        Returns:
            Filtered list of tools relevant to the query.
        """
        categories = self.classify(query)

        if categories is None:
            return all_tools

        # Collect tool names from matched categories
        tool_names = set()
        for cat_name in categories:
            cat_tools = self.categories[cat_name].get("tools", [])
            tool_names.update(cat_tools)

        # Filter all_tools to only those in matched categories
        filtered = [t for t in all_tools if t.__name__ in tool_names]

        # Safety: if filtering returned nothing, return all tools
        if not filtered:
            return all_tools

        print(f"[router] Categories: {categories} -> {len(filtered)} tools")
        return filtered
