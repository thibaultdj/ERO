# Rapport

Sommaire

1 Contexte et schéma d’implémentation  
1.1 Contexte  
1.2 Données utilisées  
1.3 Hypothèse de modélisation  
1.4 Placement des dépôts  
1.5 Formalisation et méthode de résolution  
1.6 Limites du modèle

2 Résultats et Scénarios  
2.1 Scénario 0  
2.2 Scénario 1  
2.3 Scénario 2  
2.4 Scénario 3

Sources

1 Contexte et schéma d’implémentation

1.1 Contexte   
	Montréal enregistre en moyenne 120 jours d’opérations de déneigement (1). On s’intéresse à l’optimisation des trajets des déneigeuses de la ville de Montréal et à l’impact du déneigement sur la ville et ses habitants. 

1.2 Données utilisées  
Le réseau routier de Montréal est représenté par un graphe orienté G \= (V, E) extrait d'OpenStreetMap, où :

- Chaque nœud v ∈ V correspond à une intersection et porte les coordonnées géographiques (latitude,longitude).  
- Chaque arête (u,v) ∈ E correspond à un tronçon de rue avec son attribut de longueur en mètres.  
-  Le graphe compte 19 574 nœuds et 62 101 arêtes. 

Coût Déneigeuses :

- Coût fixe : 500 CAD/jour  
- Coût kilométrique 1.1 CAD/km  
- Coût horaire 1.1 CAD/h les 8 premières heures puis 1.3 CAD/h  
- Vitesse moyenne 10km/h

1.3 Hypothèse de modélisation

- Chaque tronçon de rue doit être parcouru au moins une fois (contrainte de couverture totale).  
- Les déneigeuses partent et reviennent au même dépôt (contrainte de circuit).

	  
1.4 Placement des dépôts

- On sélectionne un milieu d'arrête au hasard parmi les arrêtes dont les nœuds font partie des 25% des nœuds au plus fort degré. Ce milieu d’arrête est notre premier centroïde.  
- Pour chaque autre milieu d'arrête restant, on calcul sa distance au centroïde le plus proche déjà choisi. On élève cette distance au carré ce qui nous donne un poids. En fonction des ces poids on trouve le centroïdes suivant a ajouter. On répète l'opération autant de fois qu’on veut de dépôts  
- Enfin chaque centroïde trouve le nœud le plus proche et sélectionne ce nœud comme dépôts. 

1.5 Formalisation et méthode de résolution

Formalisation. Soit G = (V, E) le graphe orienté d'un secteur, pondéré par la longueur ℓ(u,v) de chaque arête. On cherche un ensemble de tournées T = {T₁, …, Tₖ}, chacune partant et revenant à un dépôt dᵢ ∈ V, tel que :

- Couverture totale : ⋃ᵢ E(Tᵢ) = E, soit ∀(u,v) ∈ E, Σᵢ 𝟙[(u,v) ∈ Tᵢ] ≥ 1 — chaque arête est parcourue par au moins une tournée.
- Contrainte de durée : durée(Tᵢ) = distance(Tᵢ) / v ≤ Tmax, ∀i.
- Minimisation du coût total : min Σᵢ coût(Tᵢ), avec coût(Tᵢ) = Cfixe + Ckm·distance(Tᵢ) + Ch(durée(Tᵢ)).

C'est une généralisation orientée, multi-dépôts et multi-véhicules du Problème du Postier Chinois : sur un graphe équilibré et fortement connexe, le CPP se résout exactement en temps polynomial (circuit eulérien). Mais le découpage en plusieurs tournées sous contrainte de durée, combiné au choix des dépôts, rend le problème global NP-difficile (proche d'un Vehicle Routing Problem) — on résout donc par heuristique plutôt que par solveur exact.

Périmètre. Contraintes prises en compte : couverture totale (ci-dessus), retour au dépôt, durée max Tmax, coût (fixe + km + horaire majoré au-delà de 8h). Hors périmètre : capacité de chargement (sel), trafic/météo dynamiques, dépendance temporelle entre tournées successives.

Hypothèses. Vitesse constante v = 10 km/h, indépendante du type de rue ; réseau statique pendant l'exécution d'une tournée ; un dépôt peut desservir plusieurs déneigeuses.

Choix de modélisation — résolution par décomposition. Plutôt qu'une résolution jointe (intraitable à l'échelle de Montréal), le problème est décomposé en sous-étapes résolues séquentiellement :

1. Placement des dépôts (facility location par k-means++, cf. 1.4).
2. Partition du secteur par plus proche dépôt.
3. Subdivision récursive (k-means) si durée(secteur) > Tmax.
4. Résolution CPP par sous-graphe : connexité forte (Tarjan + Dijkstra), équilibrage des degrés (couplage glouton), circuit eulérien (Hierholzer).

Pour les scénarios priorisés (2.2 à 2.4), chaque arête reçoit un poids p(u,v) ∈ {1,2,3} qui biaise (a) le placement des dépôts vers les arêtes p=1, et (b) l'ordre de parcours du circuit eulérien (tri décroissant de priorité à chaque carrefour).

Indicateurs d'évaluation, comparant systématiquement scénario priorisé vs scénario de référence à dépôts égaux :

- distance totale, durée max vs Tmax, coût opérationnel total ;
- P90 = 90ᵉ centile de {t(u,v) : (u,v) de priorité 1}, où t(u,v) est l'instant de premier passage sur l'arête — capture le cas défavorable, pas seulement la moyenne ;
- taux de couverture cumulé par jalon horaire h : |{(u,v) priorité p : t(u,v) ≤ h}| / |{(u,v) priorité p}|.

Limites. Heuristiques sans garantie d'optimalité (k-means, couplage glouton) ; vitesse constante non réaliste ; modèle statique (pas de chute de neige continue) ; absence de contrainte de capacité. Les limites spécifiques au placement des dépôts et à l'équilibrage sont détaillées en 1.6.

La distance minimale théorique est de 6 242 km.  
		  
1.6 Limites du modèle 

- Sélection des dépôts: Le premier milieu est choisi au hasard, donc il n’est pas nécessairement optimal. Les dépôts sont forcément positionnés à des carrefour ce qui n’est pas réaliste.  
- Connexité forte: L'algorithme de Tarjan identifie les composantes fortement connexes, l'ajout d'arêtes virtuelles par Dijkstra pour relier les composantes isolées introduit des chemins qui n'existent pas physiquement. Ces arêtes peuvent créer des circuits eulériens qui passent par des nœuds hors du secteur assigné à ce dépôt.  
- Équilibrage des degrés : On compare les degrés entrant et sortant de chaque nœud. On liste les nœuds en excès et les nœuds en déficit. Pour chaque nœud excédentaire on regarde le nœud déficitaire le plus proche géographiquement. Hors le plus proche géographique n’est pas forcément le plus proche dans le graphe. 

2 Résultats et Scénarios

2.1 Scénario 0  
	Ce scénario constitue la référence pour le déneigement total de la ville. Toutes les rues reçoivent la même priorité. Les dépôts sont placés automatiquement (voir 1.4 Placement des dépôts).   
	Argumentaire : Le déneigement uniforme est l’approche réglementaire de base. Il sert de référence pour les autres scénarios.   
	Résultats : 

| Nombre de dépôts  | Nombre de déneigeuse par dépôts  | Temps nécessaire  | Prix |
| :---- | ----- | ----- | ----- |
| 1 | 1×310  | 13.45h | 185 302,87 $ |
| 5 | 1×26, 1×27, 2×28, 1×48  | 11.94h | 93 668,46 $ |
| 10 | 1×10, 3×12, 2×13, 2×14, 1×17, 1×19  | 11.94h | 80 472,82 $ |
| 15 | 2×6, 3×7, 6×9, 2×11, 1×12, 1×17  | 11.15h | 80 985,71 $ |
| 19 | 3×4, 4×5, 3×6, 5×7, 1×8, 1×9, 1×12, 1×19  | 11.98h | 78 494,55 $ |
| 20 | 3×4, 4×5, 4×6, 4×7, 2×8, 1×9, 1×10, 1×11  | 11.19h | 76 815,78 $ |
| 21 | 1×3, 4×4, 4×5, 3×6, 4×7, 1×8, 2×9, 1×10, 1×11  | 11.19h | 77 761,44 $ |
| 25 | 4×3, 5×4, 5×5, 4×6, 3×7, 2×8, 2×9  | 10.16h | 79 743,06 $ |

Conclusion : parmi les configurations testées, 20 dépôts donnent le coût opérationnel le plus bas (76 815,78$/jour). Sur 120 jours de déneigement (une saison), cela représente 9 217 893,60 $ pour Montréal. Le modèle ne tient compte ici que du coût opérationnel (carburant, heures, forfait journalier) — aucun coût d'infrastructure de dépôt n'est modélisé, donc cette conclusion ne reflète pas un arbitrage coût-opérationnel/coût-d'infrastructure : au-delà de 20 dépôts, le gain marginal en coût opérationnel diminue sans qu'un coût de construction vienne le contrebalancer dans le modèle actuel.

Avec la même méthode on trouve pour les quartiers suivants :

| Arrondissement | Dépôts | Nombre de dépôts x nombre déneigeuse | Temps nécessaire | Prix |
| :---- | ----- | ----- | ----- | ----- |
| Verdun | 1 | 1x2 | 8.66h | 1 179.63 $ |
| Outremont | 1 | 1x1 | 8.88h | 607.64 $ |
| Anjou | 1 | 1x4  | 9.61h | 2 391.05 $ |
| RDP | 2 | 2x6 | 9.72h | 7 149.25 $ |

2.2 Scénario 1  
	Ce scénario vise à déneiger en priorité les hôpitaux.   
Argumentaire : L'accessibilité des établissements de santé en période hivernale est un enjeu de sécurité publique. Les hôpitaux de Montréal accueillent des urgences 24h/24 et nécessitent une accessibilité permanente. Une route non déneigée peut retarder une ambulance ou empêcher un patient de se rendre aux soins.

Fonctionnement : Pour chaque arrondissement, on collecte les coordonnées GPS des établissements de santé (hôpitaux, CLSC, cliniques) ainsi que les zones à forte densité de population (données StatCan 2021). On calcule ensuite le plus court chemin (algorithme de Dijkstra) entre chaque établissement de santé et chaque zone dense. Les arêtes traversées par ces chemins sont marquées en priorité P1. Les dépôts sont ensuite placés par k-means++ centré sur ces corridors P1, de sorte que les déneigeuses démarrent au cœur des zones prioritaires.

	Bénéfices attendus : 

- Réduction du temps d'accès aux urgences pour les ambulances et véhicules de secours.  
- Réduction du risque de report ou d'annulation d'interventions chirurgicales planifiées.

	Risques : la concentration des dépôts sur les axes hospitaliers peut retarder le déneigement des zones résidentielles éloignées. Un surcoût est envisageable. 

Résultats par arrondissement : 

| Arrondissement | Dépôts | Config | Durée | Prix | P90 S1 | P90 S0 | Gain P90 |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| Verdun | 1 | 1x2 | 8.66h | 1 179.39 $ | 6.93h | 8.61h | −1.69h (−20%) |
| Outremont | 1 | 1x1 | 8.88h | 607.64 $ | 8.34h | 8.63h | −0.29h (−3%) |
| Anjou | 1 | 1x4 | 9.76h | 2 388.66 $ | 9.40h | 9.43h | −0.02h (−0%) |
| RDP | 2 | 1x8 / 1x6 | 9.44h | 8 183.82 $ | 9.30h | 9.53h | −0.24h (−2%) |

Observation :

Verdun est le cas le plus fort : −20% sur le P90, et à 6h, 78% des corridors santé sont déjà dégagés contre seulement 13% en S0 — l'Hôpital de Verdun et l'Institut Douglas deviennent accessibles nettement plus tôt.

RDP : à 8h, S1 a dégagé 40% des corridors contre 35% en S0 ; le gain reste modeste (−2%) mais profite à 106 000 habitants.

Outremont a un gain faible (−3%) : l'arrondissement est petit et les 2 services de santé sont en périphérie, les corridors P1 restent longs à dégager (0% de couverture avant la 6e heure dans les deux scénarios).

Anjou est le cas où la priorisation a le moins d'effet (gain quasi nul, −0%) : avec un seul dépôt, les corridors santé d'Anjou se trouvent déjà sur le chemin naturel des tournées de base (3/48 corridors dégagés dès 4h, autant en S1 qu'en S0) — la priorisation ne change quasiment rien à l'ordre de passage dans ce secteur précis.

2.3 Scénario 2  
	Ce scénario vise à déneiger en priorité les centres commerciaux et les pôles d’activité économique.   
Argumentaire : les épisodes neigeux entraînent une réduction significative de la fréquentation commerciale. La priorisation des accès commerciaux vise à maintenir l'activité économique.  
	Fonctionnement : Pour chaque arrondissement, on collecte les coordonnées GPS des commerces ainsi que les zones à forte densité de population (données StatCan 2021). On calcule ensuite le plus court chemin (algorithme de Dijkstra) entre chaque commerce et chaque zone dense. Les arêtes traversées par ces chemins sont marquées en priorité P1. Les dépôts sont ensuite placés par k-means++ centré sur ces corridors P1, de sorte que les déneigeuses démarrent au cœur des zones prioritaires.  
	Bénéfices attendus : 

- Maintien de la fréquentation des commerces par les citoyens.  
- Maintien du transport de ressources entre professionnels. 

	Risques : Le choix des zones à déneiger en priorité peut devenir politique et peut causer du tort aux commerces non sélectionnés comme prioritaires.

Résultats par arrondissement : 

| Arrondissement | Dépôts | Dépôts x Déneigeuses | Durée | Prix | P90 S2 | P90 S0 | Gain P90 |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| Verdun | 1 | 1x2 | 8.66h | 1 179.63 $ | 7.88h | 8.38h | −0.50h (−6%) |
| Outremont | 1 | 1x1 | 8.88h | 607.64 $ | 8.14h | 8.63h | −0.49h (−6%) |
| Anjou | 1 | 1x4 | 9.61h | 2 391.05 $ | 8.69h | 8.96h | −0.27h (−3%) |
| RDP | 2 | 1x8 / 1x7 | 9.65h | 8 691.71 $ | 7.33h | 8.43h | −1.10h (−13%) |

Observation : On remarque que dans ce scénario, le coût total des opérations reste presque identique au scénario de base. En revanche, le planning du déneigement change complètement pour privilégier les habitants. Par exemple, dans Rivière-des-Prairies (RDP), 49 % de la population (52 000 habitants) a un accès dégagé vers un supermarché dès la 2e heure, alors que le scénario de base est à 0 % à la même heure. On retrouve ce même écart à Verdun : à la 4e heure, notre algorithme relie 70 % des habitants aux commerces (11 corridors sur 36 terminés), contre seulement 6 % pour le scénario 0\.

Gains indirects et maintien de l'activité : Même si le temps de travail total des engins ne change pas, déneiger les routes principales en premier apporte un vrai gain économique. Selon les chiffres du commerce de détail, les grosses tempêtes d'hiver au Québec font baisser la fréquentation des magasins de 25 % à 30 % \[5\]. Le scénario 0 met 4 à 6 heures pour débloquer ces routes (comme à RDP). En les déblayant beaucoup plus vite, notre modèle protège deux éléments clés :

- Le maintien des livraisons : Les camions d'approvisionnement (produits frais, denrées importantes) accèdent plus vite aux quais de déchargement des supermarchés. Cela évite les retards en chaîne et les rayons vides, un problème bien connu en logistique urbaine.

- Le déplacement des employés : Les magasins ont besoin de leur personnel pour ouvrir. Dégager les routes prioritaires tôt le matin permet aux salariés des quartiers denses d'arriver à l'heure au travail, ce qui évite les fermetures forcées ou le recours au chômage technique.

	  
Modèle de quantification du gain économique local. Pour mesurer l’impact réel du scénario 2, au-delà des simples coûts opérationnels de transports ( qui représente néanmoins 200M de dollar en budget municipal annuel). En prenant l'exemple de l'arrondissement de Rivière-des-Prairies (106 000 habitants), notre modèle permet à 52 000 habitants d'accéder aux supermarchés et aux pharmacies 4 heures plus tôt qu'avec le scénario de base. D’après l'institut de statistique du Québec(ISQ), les dépenses moyennes en commerce s'élèvent à environ 45$ par jour par habitant. En posant l’hypothèse prudente que seulement 15% de ces 52 000 habitants ont besoin d’approvisionnement ce jour là on peut calculer:  
Gain RDP: 52 000 hab. x 15% x 45$ \= 351 000$ préservés.  
Ce résultat ne concerne que le secteur de Rivière-des-Prairies. Appliqué à l'échelle de la Ville de Montréal et de ses 19 arrondissements, le gain économique total devient majeur pour l'activité locale.

2.4 Scénario 3  
	Dans ce scénario, nous imaginons qu’une tempête de neige s'abat sur la ville et fige totalement le trafic. L'objectif n'est plus de déneiger uniformément, mais de rétablir en priorité les axes à plus forte valeur économique, de façon à limiter les pertes liées à l'arrêt de l'activité.  
	Argumentaire : lors d'une tempête majeure, la capacité de déneigement (engins, sel, équipes) est saturée et ne peut pas tout traiter simultanément. Plutôt que de répartir l'effort de manière homogène, on le concentre là où chaque heure de déneigement « rapporte » le plus : commerces, livraisons, transport en commun. Déneiger un corridor de bus rétablit la mobilité de milliers de travailleurs ; déneiger d'abord une rue résidentielle peu fréquentée a un impact économique marginal. On ordonne donc le déneigement par priorité décroissante d'impact :

- P1 : axes commerciaux et corridors de bus  
- P2 : axes secondaires à usage mixte  
- P3 : rues résidentielles à faible activité

	Fonctionnement : on n'a pas de données réelles sur les axes commerciaux ou les corridors de bus, donc on les devine via la forme du réseau. Une grande rue est traversée par beaucoup de trajets et relie des carrefours avec plusieurs branches ; une petite rue résidentielle est peu traversée et finit souvent en cul-de-sac. On calcule un score sur ces deux critères pour chaque rue : les 12% au meilleur score deviennent P1 (axes principaux), les 28% suivantes P2, le reste P3. Les dépôts sont placés près des P1, et chaque déneigeuse dégage les P1 avant les P2 puis les P3.  
Bénéfices attendus : 

- Surface de déneigement prioritaire réduite, donc dégagée plus vite  
- Rétablissement de la mobilité économique en un temps réduit  

Risques : 

- Gestion de la circulation compliquée si les rues secondaires restent enneigées longtemps  
- Pas de priorisation explicite des zones essentielles (santé) si elles ne coïncident pas avec les axes commerciaux/de transit

Résultats par arrondissement : 

| Arrondissement | Dépôts | Dépôts x Déneigeuses | Durée | Prix | P90 S3 artères | P90 S0 artères | Gain P90 |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| Verdun | 1 | 1x2 | 8.66h | 1 175.53 $ | 5.61h | 6.01h | −0.40h (−7%) |
| Outremont | 1 | 1x1 | 8.88h | 607.64 $ | 6.64h | 8.07h | −1.43h (−18%) |
| Anjou | 1 | 1x4 | 9.79h | 2 393.13 $ | 6.91h | 7.81h | −0.91h (−12%) |
| RDP | 2 | 1x6 / 1x5 | 9.98h | 6 630.09 $ | 5.82h | 7.80h | −1.97h (−25%) |

Sources :  
1 \- [montrealtips](https://montrealtips.com/fr/2025/10/10/montreal-snowfall-how-much-snow-does-montreal-get-each-year-2025-update)  
2 \- [wausauequipment](https://wausauequipment.com/municipal-equipment/snowplows/r-series/?utm_source=chatgpt.com)  
3 \- [Portail Immobilier](https://www.portail-immobilier.fr/cout-dun-batiment-industriel-au-m2-estimation-des-prix-de-construction/)  
4  \- [apdeq](https://apdeq.qc.ca/blogue/les-indicateurs-du-developpement-industriel-une-mise-a-jour-qui-simpose/)  
5 \- [cccd](https://www.commercedetail.org/)  
6 \- [isq](https://statistique.quebec.ca/fr)

