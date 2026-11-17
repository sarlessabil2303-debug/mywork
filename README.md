# MesuresApp 2.0

Un seul programme (Windows 7 compatible) pour les trois types de controle :

| Type | Remplace | Modele HTML | Rapport |
|---|---|---|---|
| Voiture essence / gazole | `bg_fixed.bat` + `process_files.ps1` + `update_report*.ps1` | `es7_essence test_merged.html` / `go1.html` | `rapport_a_imprimer.html/.pdf` |
| Bus | `trucks.bat` + `trucks_process.ps1` (bus) | `bus_go.html` | `rapport_a_imprimer.html/.pdf` |
| Camion lourd | `trucks.bat` + `trucks_process.ps1` (camion) | `camion_lourd.html` | `rapport_camion.html/.pdf` |

Deroulement (identique aux anciens scripts) : controles -> date/heure + CRC dans les fichiers de mesures ->
rapport HTML -> PDF (Google Chrome headless) -> impression (SumatraPDF, sinon lecteur PDF) -> deplacement
des fichiers vers `C:\GIEGLAN\res`. Les controles sont faits **avant** de modifier quoi que ce soit.

## Utilisation

* Double-clic sur `MesuresApp.exe` : choisir le dossier et le type de vehicule, puis "Lancer le traitement".
* Sans fenetre, comme les anciens .bat : `MesuresApp.exe --auto --type voiture|bus|camion`
  (dans le dossier des mesures, ou `--folder X`). Options : `--mode essence|gazole`, `--no-print`, `--no-pdf`, `--no-move`.
  Code de sortie 0 = succes, 1 = erreur.
* Journal : `mesures_log.txt` a cote de l'exe. Reglages : `mesures_config.json`.
* Les modeles HTML sont cherches dans le dossier des mesures, puis a cote de l'exe. Ils ne sont **pas** dans ce depot.

## Securites

* Sans fichier `.F` dans le dossier, le traitement s'arrete (aucun rapport, aucune impression, rien n'est deplace).
* Une fois les fichiers deplaces vers `res`, le rapport (HTML et PDF) est supprime pour ne pas laisser un ancien
  rapport dans le dossier. Reglage « Supprimer le rapport... » ou option `--keep-report`. Si le deplacement est
  desactive, le rapport est conserve. Un rapport deja present est de toute facon remplace au traitement suivant.

## Controle du vehicule (avant toute modification)

Le numero (matricule) est le nom des fichiers `.F/.O/.G/.R/.S`. Avant de modifier ou d'imprimer quoi que ce soit :

1. tous les fichiers de mesures du dossier doivent porter le meme numero que le `.F` le plus recent ;
2. un fichier `<numero>.cg` doit exister dans `C:\GIEGLAN\cg` (vehicule ajoute depuis l'ordinateur externe).

Sinon le traitement s'arrete avec le message « le vehicule doit d'abord etre enregistre » (numeros proches proposes : un chiffre faux, zeros en trop ou en moins).
Les numeros peuvent etre ajoutes a tout moment : le dossier cg est relu a chaque essai, et la fenetre propose **Reessayer** apres l'enregistrement.
Si le matricule a ete corrige par renommage, le controle porte sur le nouveau numero, et l'ancien nom est restaure en cas de refus.
Desactivable dans "Reglages" ou avec `--no-check`.

## CRC

Voiture/bus utilisaient `poids 1,2,3,4,5,1,2,...` et camion `poids 1,2,3,...,14`. Le programme **verifie** le calcul
sur les champs date deja presents dans les fichiers avant de les modifier, et n'utilise le calcul d'origine du type
que si les fichiers ne permettent pas de trancher (le journal indique le choix).

## Obtenir l'exe

`.github/workflows/build-exe.yml` construit l'exe (Python 3.7 + PyInstaller 5.13) :
onglet **Actions** -> dernier run -> **Artifacts**, ou nouvelle **Release** avec un tag `v2.0`.

Windows 7 : SP1 recommande, avec "Universal C Runtime" (KB2999226) si une DLL `api-ms-win-crt-*` manque.
