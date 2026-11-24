# Potencjalne poprawki

## Hasło użytkownika przy instalacji

Na świeżym Steam Decku konto `deck` często nie ma hasła. Instalator woła `sudo`, żeby dopuścić wpisywanie klawiszy (`/dev/uinput`), i wtedy system zatrzymuje się na haśle, którego nie ma.

Objaw: instalacja stoi albo pyta o hasło, a użytkownik nigdy go nie ustawiał. Trzeba ręcznie wejść w ustawienia systemu i nadać hasło.

Możliwa poprawka: przed `sudo` sprawdzić `passwd -S` (status `NP` = brak hasła). Jeśli hasła nie ma, pokazać okno z instrukcją: Ustawienia systemowe → Użytkownicy → ustaw hasło, i nie iść dalej, dopóki hasło nie powstanie.

## Nie da się przesunąć klawiatury

Przeciąganie jest zrobione przez `move()` okna (prawy przycisk albo niebieskie tło). W trybie pulpitu Steam Deck działa Wayland (KWin). KWin ignoruje takie przesuwanie — program nie może sam ustawić sobie pozycji na ekranie.

Dlatego okno zostaje tam, gdzie się pojawiło. Lewy przycisk na klawiszu i tak wpisuje znak, a nie ciągnie okna. Niebieski margines jest wąski, nawet gdyby `move()` działało.

Możliwa poprawka: przy złapaniu okna wołać `startSystemMove()` (Qt prosi KWin o przeciągnięcie). Dodać wyraźny pasek do chwycenia, nie tylko cienkie niebieskie tło.
