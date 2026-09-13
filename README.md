# OOOZet

Bot serwera [OKI OI OIJ Zjednoczenie](https://discord.gg/AMGxG4TvDS) do spełniania jego nietuzinkowych potrzeb.

## Instalacja

1. Sklonuj repozytorium za pomocą `git clone --depth 1 --recurse-submodules https://github.com/OOOZet/OOOZet`.
2. Upewnij się, że masz zainstalowanego Pythona 3.
3. Stwórz wirtualne środowisko za pomocą `python3 -m venv ./venv/`, żeby nie psuć sobie pakietów systemowych.
4. Zainstaluj potrzebne biblioteki przy użyciu `./venv/bin/pip3 install -r requirements.txt`.
5. Wsadź token swojego bota do `config.json`.
6. Ustaw inne dostępne opcje w `config.json` wedle uznania, listę których możesz znaleźć w [`common.py`](common.py#L29).
7. Odpal `./venv/bin/python3 main.py` z opcjonalną opcją `-c <ścieżka do configu>`.
8. Smacznego.

Domyślnie bot będzie zapisywał swoje dane w `database.json`, a jego konsola będzie otwarta na porcie 2341, do której możesz się podłączyć za pomocą `telnet localhost 2341`.

## Kontrybuowanie

W głównym folderze znajduje się szkielet bota, który raczej nie będziesz musiał modyfikować w bliżej nieokreślony sposób:
- [`bot.py`](bot.py) - Odpalanie instancji bota. Jedyne miejsce warte uwagi w tym pliku to [`setup_hook`](bot.py#L25), w którym inicjalizujesz swoje feature'y.
- [`common.py`](common.py) - Plik zawierający domyślny i w trakcie wykonywania załadowany `config` oraz wiele różnych narzędzi, z którymi warto się zapoznać, żeby nie pisać tego samego drugi raz. Może się zdarzyć, że w przyszłości sam dodasz coś od siebie do tej kolekcji. Jest tutaj też funkcja `redacted_config` zwracająca konfigurację oczyszczoną z wrażliwych danych, która może być później wysyłana w świat.
- [`console.py`](console.py) - Tekstowa konsola na jednym z portów TCP w pewien sposób ułatwiająca zarządzanie botem. Jedyne, co potrzebujesz do tworzenia własnych komend, to `console.begin(…)`, `console.register(…)` i `console.end()`.
- [`database.py`](database.py) - Moduł zajmujący się trzymaniem w pamięci, ładowaniem i zapisywaniem pliku JSON zwanego "bazą danych". Jedyne dwie rzeczy, które będziesz potrzebować stąd, to `database.data` i `database.should_save = True`. Typy `set` i `datetime` są automatycznie konwertowane z i na JSON podczas ładowania i zapisywania, więc w `database.data` trzymaj je w ich oryginalnej postaci. To samo dotyczy kluczy typu `int` w słownikach.
- [`main.py`](main.py) - Punkt wejściowy programu. Nie robi nic więcej jak zainicjalizowanie innych modułów.

Cała realna funkcjonalność bota jest trzymana w folderze [`features`](features/). Na początku pliku [`misc.py`](features/misc.py) znajdują się dwie funkcje, które mogą się okazać ciekawe, jeśli masz w planach, żeby bot automatycznie nadawał użytkownikom jakieś role.

Podczas programowania przydatnymi mogą się też okazać:
- Opcja `--dev`, która wyłącza powolną synchronizację listy komend bota z serwerami Discorda.
- Komenda `source ./venv/bin/activate`, dzięki której nie trzeba pisać `./venv/bin/` przed komendami Pythona.
