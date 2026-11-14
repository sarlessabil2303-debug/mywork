# MesuresApp

Remplace `bg_fixed.bat` + les scripts PowerShell (`process_files.ps1`, `update_report.ps1`,
`update_report_go_O.ps1`) par une application Windows avec interface graphique.

Ce que fait le traitement (identique au .bat) :

1. date/heure de l'ordinateur -> `ddMMyyyyHHmmss`, calcul du CRC ;
2. mise a jour de la date (`[MESURES]`) et du CRC (`[CRC]`) dans les fichiers `.F .O .G .R .S` ;
3. mode **GAZOLE** si un `.O` existe sans `.G`, sinon **ESSENCE** ;
4. remplissage du modele HTML (`es7_essence test_merged.html` ou `go1.html`) -> `rapport_a_imprimer.html` ;
5. conversion en PDF avec Google Chrome (headless), puis impression (SumatraPDF si present, sinon lecteur PDF par defaut), 2 exemplaires ;
6. deplacement des fichiers de mesures vers `C:\GIEGLAN\res`.

## Utilisation

* Double-clic sur `MesuresApp.exe` : fenetre avec dossier, options et journal.
* Sans fenetre, comme l'ancien .bat : `MesuresApp.exe --auto` (dans le dossier des mesures, ou `--folder X`).
  Options : `--no-print`, `--no-pdf`, `--no-move`, `--mode essence|gazole`. Journal : `mesures_log.txt` a cote de l'exe.

Les modeles HTML (`es7_essence test_merged.html`, `go1.html`) doivent se trouver dans le dossier des mesures
ou a cote de l'exe. Ils ne sont **pas** inclus dans ce depot.

## Obtenir l'exe

Le fichier `.github/workflows/build-exe.yml` construit l'exe sur GitHub (Python 3.8 + PyInstaller 5.13, compatible Windows 7).

* Onglet **Actions** -> dernier run -> **Artifacts** -> `MesuresApp-windows`, ou
* creer un tag (`git tag v1.0 && git push origin v1.0`) -> l'exe apparait dans **Releases**.

Windows 7 : SP1 requis, avec la mise a jour "Universal C Runtime" (KB2999226) si une DLL `api-ms-win-crt-*` manque.
