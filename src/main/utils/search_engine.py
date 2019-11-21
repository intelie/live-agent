import traceback

from duckduckapi import api

class SearchResult:
    def __init__(self, url, desc):
        self.url = url
        self.desc = desc

    def __str__(self):
        return f"{self.desc}\n{self.url}"


class SearchEngine:
    def __init__(self):
        pass

    def search(self, phrase):
        raise NotImplementedError()


class DuckEngine(SearchEngine):
    def __init__(self):
        self.client = api.DuckSyncClient()
        super().__init__()

    def search(self, phrase):
        try:
            # NOTE: Important !! phrase.upper() is required because query string values like 'AaA'
            # fail in lib requests. (is it a bug in requests?)
            # The real case was this: http://api.duckduckgo.com/?q=Diff_WOB&format=json
            # Converting the param to uppercase solves the problem for our use case.
            results = self.client.search(phrase.upper())
            return self.to_result(results)
        except Exception:
            traceback.print_exc()
            raise

    def from_duck_result(self, item):
        return SearchResult(item.first_url, item.text)

    def to_result(self, duck_result):
        res = list(map(self.from_duck_result, duck_result.related_topics))
        res = list(filter(lambda item: item.url.strip() != "", res))
        return res


class DuckFirstWordEngine(DuckEngine):
    def search(self, phrase):
        first_annotation_word = phrase.split(" ")[0]
        return super().search(first_annotation_word)


if __name__ == "__main__":
    engine = DuckEngine()
    res = engine.search("python")
    for r in res:
        print(r)
        print()
