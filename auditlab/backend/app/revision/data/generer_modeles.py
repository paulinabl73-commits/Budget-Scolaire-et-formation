"""Génère les modèles de référentiels livrés (data/*.json). Relancer après modification :
python app/revision/data/generer_modeles.py depuis backend/ (les fichiers sont écrits dans data/)."""
import json
comptes = {
 1:("Comptes de ressources durables",{"10":"Capital","11":"Réserves","12":"Report à nouveau","13":"Résultat net de l'exercice","14":"Subventions d'investissement","15":"Provisions réglementées et fonds assimilés","16":"Emprunts et dettes assimilées","17":"Dettes de location-acquisition","18":"Dettes liées à des participations et comptes de liaison","19":"Provisions financières pour risques et charges",
   "101":"Capital social","102":"Capital par dotation","103":"Capital personnel","104":"Compte de l'exploitant","105":"Primes liées au capital social","106":"Écarts de réévaluation","109":"Apporteurs, capital souscrit non appelé","111":"Réserve légale","112":"Réserves statutaires ou contractuelles","113":"Réserves réglementées","118":"Autres réserves"}),
 2:("Comptes d'actif immobilisé",{"21":"Immobilisations incorporelles","22":"Terrains","23":"Bâtiments, installations techniques et agencements","24":"Matériel, mobilier et actifs biologiques","245":"Matériel de transport","25":"Avances et acomptes versés sur immobilisations","26":"Titres de participation","27":"Autres immobilisations financières","28":"Amortissements","281":"Amortissements des immobilisations incorporelles","282":"Amortissements des terrains","283":"Amortissements des bâtiments, installations et agencements","284":"Amortissements du matériel","2845":"Amortissements du matériel de transport","29":"Dépréciations des immobilisations","291":"Dépréciations des immobilisations incorporelles","292":"Dépréciations des terrains","293":"Dépréciations des bâtiments","294":"Dépréciations du matériel","295":"Dépréciations des avances et acomptes sur immobilisations","296":"Dépréciations des titres de participation","297":"Dépréciations des autres immobilisations financières"}),
 3:("Comptes de stocks",{"31":"Marchandises","32":"Matières premières et fournitures liées","33":"Autres approvisionnements","34":"Produits en cours","35":"Services en cours","36":"Produits finis","37":"Produits intermédiaires et résiduels","38":"Stocks en cours de route, en consignation ou en dépôt","39":"Dépréciations des stocks et encours de production"}),
 4:("Comptes de tiers",{"40":"Fournisseurs et comptes rattachés","401":"Fournisseurs, dettes en compte","409":"Fournisseurs débiteurs","41":"Clients et comptes rattachés","411":"Clients","419":"Clients créditeurs","42":"Personnel","43":"Organismes sociaux","44":"État et collectivités publiques","45":"Organismes internationaux","46":"Apporteurs, associés et groupe","47":"Débiteurs et créditeurs divers","478":"Écarts de conversion – actif","479":"Écarts de conversion – passif","48":"Créances et dettes hors activités ordinaires","481":"Fournisseurs d'investissements","482":"Fournisseurs d'investissements, effets à payer","484":"Autres dettes HAO","485":"Créances sur cessions d'immobilisations","488":"Autres créances HAO","49":"Dépréciations et provisions pour risques à court terme (tiers)","491":"Dépréciations des comptes clients","499":"Provisions pour risques à court terme"}),
 5:("Comptes de trésorerie",{"50":"Titres de placement","51":"Valeurs à encaisser","52":"Banques","53":"Établissements financiers et assimilés","54":"Instruments de trésorerie","55":"Instruments de monnaie électronique","56":"Banques, crédits de trésorerie et d'escompte","564":"Escompte de crédits de campagne","565":"Escompte de crédits ordinaires","57":"Caisse","58":"Régies d'avances, accréditifs et virements internes","59":"Dépréciations et provisions pour risques à court terme (trésorerie)","590":"Dépréciations des titres de placement","599":"Provisions pour risques à court terme à caractère financier"}),
 6:("Comptes de charges des activités ordinaires",{"60":"Achats et variations de stocks","601":"Achats de marchandises","602":"Achats de matières premières et fournitures liées","603":"Variations des stocks de biens achetés","6031":"Variations des stocks de marchandises","6032":"Variations des stocks de matières premières","6033":"Variations des stocks d'autres approvisionnements","604":"Achats stockés de matières et fournitures consommables","605":"Autres achats","608":"Achats d'emballages","61":"Transports","62":"Services extérieurs A","63":"Services extérieurs B","64":"Impôts et taxes","65":"Autres charges","66":"Charges de personnel","67":"Frais financiers et charges assimilées","68":"Dotations aux amortissements","681":"Dotations aux amortissements d'exploitation","69":"Dotations aux provisions et aux dépréciations","691":"Dotations aux provisions et dépréciations d'exploitation","697":"Dotations aux provisions et dépréciations financières"}),
 7:("Comptes de produits des activités ordinaires",{"70":"Ventes","701":"Ventes de marchandises","702":"Ventes de produits finis","703":"Ventes de produits intermédiaires","704":"Ventes de produits résiduels","705":"Travaux facturés","706":"Services vendus","707":"Produits accessoires","71":"Subventions d'exploitation","72":"Production immobilisée","73":"Variations des stocks de biens et de services produits","75":"Autres produits","77":"Revenus financiers et produits assimilés","78":"Transferts de charges","781":"Transferts de charges d'exploitation","787":"Transferts de charges financières","79":"Reprises de provisions, de dépréciations et autres","791":"Reprises de provisions et dépréciations d'exploitation","797":"Reprises de provisions et dépréciations financières","798":"Reprises d'amortissements","799":"Reprises de subventions d'investissement"}),
 8:("Comptes des autres charges et des autres produits",{"81":"Valeurs comptables des cessions d'immobilisations","82":"Produits des cessions d'immobilisations","83":"Charges hors activités ordinaires","84":"Produits hors activités ordinaires","85":"Dotations hors activités ordinaires","86":"Reprises hors activités ordinaires","87":"Participation des travailleurs","88":"Subventions d'équilibre","89":"Impôts sur le résultat"}),
 9:("Comptes des engagements hors bilan et de la comptabilité analytique",{"90":"Engagements obtenus et engagements accordés","91":"Comptes réfléchis","92":"Comptes de reclassements","93":"Comptes de coûts","94":"Comptes de stocks (analytique)","95":"Comptes d'écarts sur coûts préétablis","96":"Comptes de différences de traitement comptable","97":"Comptes de résultats analytiques","98":"Comptes de liaisons internes","99":"Comptes de l'activité"}),
}
accounts=[]
for classe,(lib,items) in comptes.items():
    accounts.append({"numero":str(classe),"libelle":lib,"classe":classe})
    for num,l in items.items():
        accounts.append({"numero":num,"libelle":l,"classe":classe})
def r(*xs, sens=None): return [{"racine":x,"sens":sens} for x in xs]
lines=[]
def L(etat,code,lib,nature,racines=(),formule=None,niveau=1):
    lines.append({"etat":etat,"code":code,"libelle":lib,"nature":nature,"racines":list(racines),"formule":formule,"ordre":len(lines)+1,"niveau":niveau})
A="bilan_actif"
L(A,"AD","Immobilisations incorporelles","actif",r("21","281","291"))
L(A,"AJ","Terrains","actif",r("22","282","292"))
L(A,"AK","Bâtiments, installations techniques et agencements","actif",r("23","283","293"))
L(A,"AM","Matériel, mobilier et actifs biologiques","actif",r("24","284","294"))
L(A,"AN","Matériel de transport","actif",r("245","2845","2945"))
L(A,"AP","Avances et acomptes versés sur immobilisations","actif",r("25","295"))
L(A,"AR","Titres de participation","actif",r("26","296"))
L(A,"AS","Autres immobilisations financières","actif",r("27","297"))
L(A,"AZ","TOTAL ACTIF IMMOBILISÉ","actif",formule="AD+AJ+AK+AM+AN+AP+AR+AS",niveau=0)
L(A,"BA","Actif circulant HAO","actif",r("485","488"))
L(A,"BB","Stocks et encours","actif",r("3"))
L(A,"BH","Fournisseurs, avances versées","actif",r("409")+r("40",sens="debit"))
L(A,"BI","Clients","actif",r("41","491",sens=None)[1:]+r("41",sens="debit")+r("411","491"))
L(A,"BJ","Autres créances","actif",r("42","43","44","45","46","47","48",sens="debit"))
L(A,"BK","TOTAL ACTIF CIRCULANT","actif",formule="BA+BB+BH+BI+BJ",niveau=0)
L(A,"BQ","Titres de placement","actif",r("50","590"))
L(A,"BR","Valeurs à encaisser","actif",r("51"))
L(A,"BS","Banques, chèques postaux, caisse et assimilés","actif",r("52","53","54","55","57","58",sens="debit"))
L(A,"BT","TOTAL TRÉSORERIE-ACTIF","actif",formule="BQ+BR+BS",niveau=0)
L(A,"BU","Écart de conversion-actif","actif",r("478"))
L(A,"BZ","TOTAL GÉNÉRAL ACTIF","actif",formule="AZ+BK+BT+BU",niveau=0)
P="bilan_passif"
L(P,"CA","Capital","passif",r("101","102","103","104"))
L(P,"CB","Apporteurs capital non appelé (−)","passif",r("109"))
L(P,"CD","Primes liées au capital social","passif",r("105"))
L(P,"CE","Écarts de réévaluation","passif",r("106"))
L(P,"CF","Réserves indisponibles","passif",r("111","112"))
L(P,"CG","Réserves libres","passif",r("113","118","11"))
L(P,"CH","Report à nouveau","passif",r("12"))
L(P,"CJ","Résultat net de l'exercice","passif",r("13"),formule="XI")
L(P,"CL","Subventions d'investissement","passif",r("14"))
L(P,"CM","Provisions réglementées","passif",r("15"))
L(P,"CP","TOTAL CAPITAUX PROPRES ET RESSOURCES ASSIMILÉES","passif",formule="CA+CB+CD+CE+CF+CG+CH+CJ+CL+CM",niveau=0)
L(P,"DA","Emprunts et dettes financières diverses","passif",r("16","18"))
L(P,"DB","Dettes de location-acquisition","passif",r("17"))
L(P,"DC","Provisions pour risques et charges","passif",r("19"))
L(P,"DD","TOTAL DETTES FINANCIÈRES ET RESSOURCES ASSIMILÉES","passif",formule="DA+DB+DC",niveau=0)
L(P,"DF","TOTAL RESSOURCES STABLES","passif",formule="CP+DD",niveau=0)
L(P,"DH","Dettes circulantes HAO","passif",r("481","482","484"))
L(P,"DI","Clients, avances reçues","passif",r("419")+r("41",sens="credit"))
L(P,"DJ","Fournisseurs d'exploitation","passif",r("40",sens="credit"))
L(P,"DK","Dettes fiscales et sociales","passif",r("42","43","44",sens="credit"))
L(P,"DM","Autres dettes","passif",r("45","46","47","48",sens="credit"))
L(P,"DN","Provisions pour risques à court terme","passif",r("499","599"))
L(P,"DP","TOTAL PASSIF CIRCULANT","passif",formule="DH+DI+DJ+DK+DM+DN",niveau=0)
L(P,"DQ","Banques, crédits d'escompte","passif",r("564","565"))
L(P,"DR","Banques, établissements financiers et crédits de trésorerie","passif",r("56")+r("52","53","54","55","57","58",sens="credit"))
L(P,"DT","TOTAL TRÉSORERIE-PASSIF","passif",formule="DQ+DR",niveau=0)
L(P,"DV","Écart de conversion-passif","passif",r("479"))
L(P,"DZ","TOTAL GÉNÉRAL PASSIF","passif",formule="DF+DP+DT+DV",niveau=0)
C="compte_resultat"
L(C,"TA","Ventes de marchandises","produit",r("701"))
L(C,"RA","Achats de marchandises","charge",r("601"))
L(C,"RB","Variation de stocks de marchandises","charge",r("6031","603"))
L(C,"XA","MARGE COMMERCIALE","produit",formule="TA-RA-RB",niveau=0)
L(C,"TB","Ventes de produits fabriqués","produit",r("702","703","704"))
L(C,"TC","Travaux, services vendus","produit",r("705","706"))
L(C,"TD","Produits accessoires","produit",r("707","70"))
L(C,"XB","CHIFFRE D'AFFAIRES","produit",formule="TA+TB+TC+TD",niveau=0)
L(C,"TE","Production stockée (ou déstockage)","produit",r("73"))
L(C,"TF","Production immobilisée","produit",r("72"))
L(C,"TG","Subventions d'exploitation","produit",r("71"))
L(C,"TH","Autres produits","produit",r("75"))
L(C,"TI","Transferts de charges d'exploitation","produit",r("781","78"))
L(C,"RC","Achats de matières premières et fournitures liées","charge",r("602"))
L(C,"RD","Variation de stocks de matières premières","charge",r("6032"))
L(C,"RE","Autres achats","charge",r("604","605","608","60"))
L(C,"RF","Variation de stocks d'autres approvisionnements","charge",r("6033"))
L(C,"RG","Transports","charge",r("61"))
L(C,"RH","Services extérieurs","charge",r("62","63"))
L(C,"RI","Impôts et taxes","charge",r("64"))
L(C,"RJ","Autres charges","charge",r("65"))
L(C,"XC","VALEUR AJOUTÉE","produit",formule="XA+TB+TC+TD+TE+TF+TG+TH+TI-RC-RD-RE-RF-RG-RH-RI-RJ",niveau=0)
L(C,"RK","Charges de personnel","charge",r("66"))
L(C,"XD","EXCÉDENT BRUT D'EXPLOITATION","produit",formule="XC-RK",niveau=0)
L(C,"TJ","Reprises d'amortissements, provisions et dépréciations","produit",r("791","798","799","79"))
L(C,"RL","Dotations aux amortissements, provisions et dépréciations","charge",r("681","691","68","69"))
L(C,"XE","RÉSULTAT D'EXPLOITATION","produit",formule="XD+TJ-RL",niveau=0)
L(C,"TK","Revenus financiers et assimilés","produit",r("77"))
L(C,"TL","Reprises de provisions et dépréciations financières","produit",r("797"))
L(C,"TM","Transferts de charges financières","produit",r("787"))
L(C,"RM","Frais financiers et charges assimilées","charge",r("67"))
L(C,"RN","Dotations aux provisions et dépréciations financières","charge",r("697"))
L(C,"XF","RÉSULTAT FINANCIER","produit",formule="TK+TL+TM-RM-RN",niveau=0)
L(C,"XG","RÉSULTAT DES ACTIVITÉS ORDINAIRES","produit",formule="XE+XF",niveau=0)
L(C,"TN","Produits des cessions d'immobilisations","produit",r("82"))
L(C,"TO","Autres produits HAO","produit",r("84","86","88"))
L(C,"RO","Valeurs comptables des cessions d'immobilisations","charge",r("81"))
L(C,"RP","Autres charges HAO","charge",r("83","85"))
L(C,"XH","RÉSULTAT HORS ACTIVITÉS ORDINAIRES","produit",formule="TN+TO-RO-RP",niveau=0)
L(C,"RQ","Participation des travailleurs","charge",r("87"))
L(C,"RS","Impôts sur le résultat","charge",r("89"))
L(C,"XI","RÉSULTAT NET","produit",formule="XG+XH-RQ-RS",niveau=0)
# BI: racines « 411 » et « 491 », plus « 41 » au solde débiteur
for l in lines:
    if l["code"]=="BI": l["racines"]=r("491")+r("41",sens="debit")
ratios=[
 {"code":"liquidite_generale","libelle":"Liquidité générale","formule":"(BK+BT)/(DP+DT)","unite":"ratio","famille":"liquidite"},
 {"code":"liquidite_immediate","libelle":"Liquidité immédiate","formule":"BT/(DP+DT)","unite":"ratio","famille":"liquidite"},
 {"code":"autonomie_financiere","libelle":"Autonomie financière (capitaux propres / total bilan)","formule":"CP/BZ","unite":"pourcentage","famille":"solvabilite"},
 {"code":"endettement","libelle":"Endettement (dettes financières / capitaux propres)","formule":"DD/CP","unite":"ratio","famille":"solvabilite"},
 {"code":"rentabilite_nette","libelle":"Rentabilité nette (résultat / chiffre d'affaires)","formule":"XI/XB","unite":"pourcentage","famille":"rentabilite"},
 {"code":"rentabilite_capitaux","libelle":"Rentabilité des capitaux propres","formule":"XI/CP","unite":"pourcentage","famille":"rentabilite"},
 {"code":"delai_clients","libelle":"Délai de recouvrement clients (jours)","formule":"BI/XB*360","unite":"jours","famille":"delais"},
 {"code":"delai_fournisseurs","libelle":"Délai de paiement fournisseurs (jours)","formule":"DJ/(RA+RC+RE)*360","unite":"jours","famille":"delais"},
]
bases=[
 {"code":"total_bilan","pct_min":"1","pct_max":"2","libelle":"Total du bilan","formule":"BZ"},
 {"code":"chiffre_affaires","pct_min":"0.5","pct_max":"2","libelle":"Chiffre d'affaires","formule":"XB"},
 {"code":"resultat","pct_min":"5","pct_max":"10","libelle":"Résultat net","formule":"XI"},
 {"code":"capitaux_propres","pct_min":"1","pct_max":"5","libelle":"Capitaux propres","formule":"CP"},
]
regles=[
 {"code":"bilan_equilibre","libelle":"Le bilan est équilibré (total actif = total passif)","gauche":"BZ","droite":"DZ"},
 {"code":"resultat_concordant","libelle":"Le résultat du bilan est égal au résultat du compte de résultat","gauche":"CJ","droite":"XI"},
]
doc={"code":"SYSCOHADA","version":"2017","libelle":"SYSCOHADA révisé – Système normal","pays":"OHADA","date_effet":"2018-01-01",
     "source":"Acte uniforme relatif au droit comptable et à l'information financière du 26 janvier 2017 (plan de comptes par racines, modèles du Système normal). Modèle de départ à contrôler et compléter par import du plan détaillé de l'entité.",
     "comptes":accounts,"postes":lines,"ratios":ratios,"bases_seuil":bases,"regles":regles,"parametres":[]}
json.dump(doc,open(__import__("os").path.join(__import__("os").path.dirname(__file__), "syscohada_2017.json"),"w"),ensure_ascii=False,indent=1)
print(len(accounts),len(lines))
# CIPRES : squelette à compléter
cip_accounts=[{"numero":str(c),"libelle":l,"classe":c} for c,l in [(1,"Capitaux propres, réserves et ressources durables"),(2,"Immobilisations"),(3,"Stocks"),(4,"Tiers (cotisants, allocataires, pensionnés)"),(5,"Trésorerie et placements"),(6,"Charges (prestations et gestion)"),(7,"Produits (cotisations et autres)"),(8,"Autres charges et produits")]]
cip_lines=[]
def CL(etat,code,lib,nature,racines=(),formule=None,niveau=1):
    cip_lines.append({"etat":etat,"code":code,"libelle":lib,"nature":nature,"racines":list(racines),"formule":formule,"ordre":len(cip_lines)+1,"niveau":niveau})
CL("bilan_actif","IM","Immobilisations nettes","actif",r("2"))
CL("bilan_actif","ST","Stocks","actif",r("3"))
CL("bilan_actif","CR","Créances (cotisants et autres)","actif",r("4",sens="debit"))
CL("bilan_actif","TA","Trésorerie et placements","actif",r("5",sens="debit"))
CL("bilan_actif","TAZ","TOTAL ACTIF","actif",formule="IM+ST+CR+TA",niveau=0)
CL("bilan_passif","RE","Réserves et ressources durables","passif",r("1"),formule="RN")
CL("bilan_passif","DE","Dettes (prestataires, allocataires et autres)","passif",r("4",sens="credit"))
CL("bilan_passif","TP","Trésorerie-passif","passif",r("5",sens="credit"))
CL("bilan_passif","TPZ","TOTAL PASSIF","passif",formule="RE+DE+TP",niveau=0)
CL("compte_resultat","PC","Produits (cotisations et autres)","produit",r("7","8",sens="credit"))
CL("compte_resultat","CH","Charges (prestations, gestion et autres)","charge",r("6")+r("8",sens="debit"))
CL("compte_resultat","RN","RÉSULTAT NET","produit",formule="PC-CH",niveau=0)
cip={"code":"CIPRES","version":"modele","libelle":"Plan comptable CIPRES – modèle de structure à compléter","pays":"CIPRES","date_effet":"2018-01-01",
 "source":"Squelette par classes. Le plan comptable CIPRES en vigueur, les états de la CIPRES, les taux, plafonds et limites sont à obtenir auprès de la CIPRES puis à importer (classeur Excel).",
 "branches":[{"code":"PF","libelle":"Prestations familiales"},{"code":"RP","libelle":"Risques professionnels"},{"code":"PV","libelle":"Pensions de vieillesse, d'invalidité et de décès"},{"code":"AM","libelle":"Assurance maladie"},{"code":"GA","libelle":"Gestion administrative"}],
 "comptes":cip_accounts,"postes":cip_lines,
 "ratios":[{"code":"autonomie","libelle":"Réserves / total bilan","formule":"RE/TAZ","unite":"pourcentage","famille":"solvabilite"}],
 "bases_seuil":[{"code":"total_bilan","pct_min":"1","pct_max":"2","libelle":"Total du bilan","formule":"TAZ"},{"code":"cotisations","pct_min":"0.5","pct_max":"2","libelle":"Cotisations (produits)","formule":"PC"},{"code":"resultat","pct_min":"5","pct_max":"10","libelle":"Résultat net","formule":"RN"}],
 "regles":[{"code":"bilan_equilibre","libelle":"Le bilan est équilibré","gauche":"TAZ","droite":"TPZ"}],
 "parametres":[]}
json.dump(cip,open(__import__("os").path.join(__import__("os").path.dirname(__file__), "cipres_modele.json"),"w"),ensure_ascii=False,indent=1)
