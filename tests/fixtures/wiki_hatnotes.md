# Live hatnote sample

Retrieved from the Russian Wikipedia API on 2026-09-05 using `prop=extracts`,
`explaintext=1`, `exintro=1`. `wiki_hatnotes.json` preserves the five extracts.
Wikipedia text is available under CC BY-SA; article histories list contributors:

- [Angel Beats!](https://ru.wikipedia.org/wiki/Angel_Beats!)
- [Black Butler](https://ru.wikipedia.org/wiki/Black_Butler)
- [Code Geass](https://ru.wikipedia.org/wiki/Code_Geass)
- [Steins;Gate](https://ru.wikipedia.org/wiki/Steins;Gate)
- [Run Rabbit Run](https://ru.wikipedia.org/wiki/Run_Rabbit_Run)

The first four came from a request for Russian anime names with `redirects=1`.
Their saved `redirects` lists contain the API-confirmed Russian request names,
converted from the response's `query.redirects` into per-page lists.
Run Rabbit Run was found using `insource:"Не путать с" фильм`, then retrieved
with `prop=extracts|redirects|pageprops`. Its Russian redirect was also verified
in a separate single-title request. The sample excludes Cyrillic headings,
disambiguation pages, and candidates without a confirmed Cyrillic redirect.

Manual inspection of the opening paragraphs, independently of `unhatted`, found
one handwritten pointer: the first line of Run Rabbit Run, 67 characters long.
The other four articles start with their own names. No inventoried pointer was
unrecognized. This is one observed form, not a census of all Wikipedia hatnotes.

Before changing the reader, the paired run found **1 differing verdict in 5
articles**, with **1 article carrying a hatnote**. Run Rabbit Run is a song;
the old reader accepted it only because the pointer mentioned somebody else's
film. Removing the pointer changed its returned title from `Run Rabbit Run`
to the empty string. The four anime/novel/manga controls retained their titles.

Reproduce offline:

```sh
.venv/bin/python scripts/hatnoteprobe.py tests/fixtures/wiki_hatnotes.json
```

To refresh, copy the snapshot to a temporary file and pass that file with
`--live`. The tool compares the historical raw reader with the cleaned reader;
exit status 1 reports a difference or an unrecognized inventoried pointer.
Network access is never part of the tests or the gate.

The length inventory is `{67: 1}`, maximum 67. It does not establish an optimal
cutoff or the prevalence of long hatnotes. The separate constructed regression
in `test_unhatted.py` demonstrates why raising the cutoff to 4000 loses an
article's description when a pointer and its lead share a paragraph. The test
protects that behavior; it does not assert that the constant must equal 240.
