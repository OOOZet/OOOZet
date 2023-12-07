# OOOZet

Bot serwera [OKI OI OIJ Zjednoczenie](https://discord.gg/AMGxG4TvDS) do spełniania jego nietuzinkowych potrzeb.

## Instalacja

1. Upewnij się, że masz zainstalowanego Pythona 3.
2. Zainstaluj discord.py 2.x, co możesz zrobić z `pip3 install -r requirements.txt`.
3. Wsadź token swojego bota do `config.json`.
4. Ustaw inne dostępne opcje w `config.json` wedle uznania, listę których możesz znaleźć w [`common.py`](common.py#L23).
5. Odpal `./main.py` lub `./main.py -c <path to config>`.
6. Smacznego.

Domyślnie bot będzie zapisywał swoje dane w `database.json`, a jego konsola będzie otwarta na porcie 4123, do której możesz się podłączyć za pomocą `telnet localhost 4123`. Cały kod został zaprojektowany z myślą, że bot będzie działać tylko na jednym serwerze na raz.

## Kontrybuowanie

W głównym folderze znajduje się szkielet bota, który raczej nie będziesz musiał modyfikować w bliżej nieokreślony sposób:
- [`bot.py`](bot.py) - Odpalanie instancji bota. Jedyne miejsce warte uwagi w tym pliku to [`setup_hook`](bot.py#L24), w którym inicjalizujesz swoje feature'y.
- [`common.py`](common.py) - Plik zawierający domyślny i w trakcie wykonywania załadowany `config` oraz wiele różnych narzędzi, z którymi warto się zapoznać, żeby nie pisać tego samego drugi raz. Może się zdarzyć, że w przyszłości sam dodasz coś od siebie do tej kolekcji.
- [`console.py`](console.py) - Tekstowa konsola na jednym z portów TCP w pewien sposób ułatwiająca zarządzanie botem. Jedyne, co potrzebujesz do tworzenia własnych komend, to `console.begin(…)`, `console.register(…)` i `console.end()`.
- [`database.py`](database.py) - Moduł zajmujący się trzymaniem w pamięci, ładowaniem i zapisywaniem pliku JSON zwanego "bazą danych". Jedyne dwie rzeczy, które będziesz potrzebować stąd, to `database.data` i `database.should_save = True`. Typy `set` i `datetime` są automatycznie konwertowane z i na JSON podczas ładowania i zapisywania, więc w `database.data` trzymaj je w ich oryginalnej postaci. To samo dotyczy kluczy typu `int` w słownikach.
- [`main.py`](main.py) - Punkt wejściowy programu. Nie robi nic więcej jak zainicjalizowanie innych modułów.

Cała realna funkcjonalność bota jest trzymana w folderze [`features`](features/). Na początku pliku [`misc.py`](features/misc.py) znajdują się dwie funkcje, które mogą się okazać ciekawe, jeśli masz w planach, żeby bot automatycznie nadawał użytkownikom jakieś role.
