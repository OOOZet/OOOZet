# OOOZet

Bot serwera [OKI OI OIJ Zjednoczenie](https://discord.gg/AMGxG4TvDS) do spełniania jego nietuzinkowych potrzeb.

## Setup

1. Upewnij się, że masz zainstalowanego Pythona 3.
2. Zainstaluj discord.py 2.x, co możesz zrobić z `pip3 install -r requirements.txt`.
3. Wsadź token swojego bota do `config.json`.
4. Ustaw inne dostępne opcje w `config.json` wedle uznania, listę których możesz znaleźć w [`common.py`](common.py#L23).
5. Odpal `./main.py` lub `./main.py -c <path to config>`.
6. Smacznego.

Domyślnie bot będzie zapisywał swoje dane w `database.json`, a jego konsola będzie otwarta na porcie 4123, do której możesz się podłączyć za pomocą `telnet localhost 4123`. Cały kod został zaprojektowany z myślą, że bot będzie działać tylko na jednym serwerze na raz.
