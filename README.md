# OOOZet

Bot serwera [OKI OI OIJ Zjednoczenie](https://discord.gg/AMGxG4TvDS) do spełniania jego nietuzinkowych potrzeb. Tam też można zobaczyć jego pełną gamę możliwości.

## Instalacja

1. Sklonuj repozytorium za pomocą `git clone --depth 1 --recurse-submodules https://github.com/OOOZet/OOOZet`.
2. Upewnij się, że masz zainstalowanego Pythona 3 z pip.
3. Stwórz wirtualne środowisko za pomocą `python3 -m venv ./venv/`, żeby nie psuć sobie pakietów systemowych.
4. Zainstaluj potrzebne biblioteki przy użyciu `./venv/bin/pip3 install -r requirements.txt`.
5. Wsadź token swojego bota do `config.json`.
6. Ustaw inne dostępne opcje w `config.json` wedle uznania, listę których możesz znaleźć w [`common.py`](src/common.py#L30).
7. Odpal `./venv/bin/python3 src/main.py` z opcjonalną opcją `-c <ścieżka do configu>`.
8. Smacznego.

Domyślnie bot będzie zapisywał swoje dane w `database.json`, a jego konsola będzie otwarta na porcie 2341, do której możesz się podłączyć za pomocą `telnet localhost 2341`.

## Kontrybuowanie

Cała realna funkcjonalność bota jest trzymana w folderze `features`. Każdy moduł w nim jest zwany "featurem". Do głównej klasy bota w [`bot.py`](src/bot.py) została dodana szczypta metaprogrammingu, aby uprościć tworzenie feature'ów poprzez automatyczną rejestrację tworzonych obiektów i wstrzykiwanie często używanych zmiennych. Poniżej chronologiczny opis procesu inicjalizacji bota:
1. Funkcja main ładuje `config` i podstawowe moduły.
2. Funkcja main importuje wszystkie feature'y. To jest późna pora na importowanie modułów w Pythonie, ale dzięki temu top-level kod w feature'ach ma dostęp do gotowego configa, a to jest potrzebne m.in. w definicjach komend ograniczonych do jednego guilda.
1. Główna klasa bota wykrywa i zapamiętuje zaimportowane moduły z prefiksem `features.`.
2. discord.py przygotowuje pętlę async i otwiera połączenie z Discordem.
3. Do globalnego scope'u feature'ów wstrzykiwane są zmienne podane niżej.
4. Zmienne globalne każdego z feature'ów są iterowane i wartości o typach podanych niżej są automatycznie rejestrowane.
5. Wyemitowany zostaje event `setup`.
6. Zarejestrowane dotąd komendy są synchronizowane z Discordem i rozpoczyna się normalna pętla wydarzeń.

Wstrzykiwane zmienne globalne:
- `bot` - Referencja do głównej klasy bota
- `feature_id` - Nazwa modułu bez prefiksu

Automatycznie rejestrowane wartości w zmiennych globalnych:
- `app_commands.Group`
- `app_commands.Command`, jeśli nie są już w jakiejś grupie.
- `common.Loop` - Tu "rejestracja" oznacza wystartowanie pętli.
- `console.Operation`, automatycznie ustawiając w nich `scope`.
- Funkcje oznaczone dekoratorem `common.event_listener`

Jak to dokładnie przekłada się na pisany kod, najlepiej zobaczyć zaglądając w kod któregoś z istniejących feature'ów.

W głównym folderze znajduje się szkielet bota, który raczej nie będziesz musiał modyfikować w bliżej nieokreślony sposób:
- [`bot.py`](src/bot.py) - Wyżej wspomniana główna klasa bota.
- [`common.py`](src/common.py) - Plik zawierający domyślny i w trakcie wykonywania załadowany `config` oraz wiele różnych narzędzi, z którymi warto się zapoznać, żeby nie pisać tego samego drugi raz. Może się zdarzyć, że w przyszłości sam dodasz coś od siebie do tej kolekcji. Jest tutaj też funkcja `redacted_config` zwracająca konfigurację oczyszczoną z wrażliwych danych, która może być później wysyłana w świat.
- [`console.py`](src/console.py) - Tekstowa konsola na jednym z portów TCP w pewien sposób ułatwiająca zarządzanie botem. Jedyne, co potrzebujesz do tworzenia własnych komend, to dekorator `console.operation(…)` i ewentualnie `console.register(…)`, jeśli tworzysz je w sposób niedostępny dla standardowej automatycznej rejestracji feature'ów.
- [`database.py`](src/database.py) - Moduł zajmujący się trzymaniem w pamięci, ładowaniem i zapisywaniem pliku JSON zwanego "bazą danych". Jedyne dwie rzeczy, które będziesz potrzebować stąd, to `database.data` i `database.should_save = True`. Typy `set` i `datetime` są automatycznie konwertowane z i na JSON podczas ładowania i zapisywania, więc w `database.data` trzymaj je w ich oryginalnej postaci. To samo dotyczy kluczy typu `int` w słownikach.
- [`main.py`](src/main.py) - Punkt wejściowy programu. Nie robi nic więcej jak zainicjalizowanie innych modułów.

Na początku pliku [`features/misc.py`](src/features/misc.py) znajdują się dwie funkcje, które mogą się okazać ciekawe, jeśli masz w planach, żeby bot automatycznie nadawał użytkownikom jakieś role.

Podczas programowania przydatnymi mogą się też okazać:
- Opcja `--dev`, która wyłącza powolną synchronizację listy komend bota z serwerami Discorda.
- Komenda `source ./venv/bin/activate`, dzięki której nie trzeba ciągle pisać `./venv/bin/` przed komendami Pythona.
