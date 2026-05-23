~Version
#MNEM .UNIT                VALUE  : DESCRIPTION                    
 VERS .                      3.0  : CWLS LOG ASCII STANDARD - VERSION 3.0 
 WRAP .                       NO  : ONE LINE PER DEPTH STEP        
 DLM  .                    COMMA  : DELIMITING CHARACTER (SPACE TAB OR COMMA) 

~Well
#MNEM .UNIT                                                           VALUE  : DESCRIPTION                    {FORMAT} | ASSOCIATION
 STRT  .F                                                             4195.0  : START DEPTH                    {F}
 STOP  .F                                                             5042.0  : END DEPTH                      {F}
 STEP  .F                                                                0.5  : STEP LENGTH                    {F}
 NULL  .                                                             -999.25  : NULL VALUE                     {F}
 COMP  .                                           MURFIN DRILLING CO., INC.  : Company                        {S}
 WELL  .                                                   CULWELL UNIT 4-32  : Well Name                      {S}
 FLD   .                                                               RAILE  : Field                          {S}
 SEC   .                                                                  32  : Section                        {I}
 TOWN  .                                                                  2S  : Township (e.g. 42S)            {S}
 RANG  .                                                                 41W  : Range  (e.g. 25E)              {S}
 LOC   .          Current operator: Murfin Drilling Co., Inc. ; Field: Raile  : Location (Sec Town Range)      {S}
 LOC1  .                                                                      : Location 1 (quarter calls)     {S}
 LOC2  .                                                                      : Location 2 (footages)          {S}
 COUN  .                                                            CHEYENNE  : County                         {S}
 STAT  .                                                              Kansas  : State                          {S}
 CTRY  .                                                                  US  : Country                        {S}
 PROV  .                                                                      : Province                       {S}
 SRVC  .                                                                      : Service Company                {S}
 LIC   .                                                                      : License Number                 {S}
 DATE  .                                                          12/22/2005  : Completion Date                {DD/MM/YYYY}
 API   .                                                        15-023-20386  : API-Number                     {S}
 UWI   .                                                                      : Unique Well ID Number          {S}
 LATI  .DEG                                                       39.8339312  : Latitude                       {F}
 LONG  .DEG                                                     -101.9452045  : Longitude                      {F}
 GDAT  .                                                               NAD27  : Geodetic Datum                 {S}
 X     .                                                           247963.17  : X or East-West coordinate      {F}
 Y     .                                                          4413267.21  : Y or North South coordinate    {F}
 HZCS  .                                                                 UTM  : Horizontal Co-ordinate System  {S}
 UTM   .                                                                14.0  : UTM Location                   {F}
 STUS  .                                                                 OIL  : Well Status                    {S}

~Parameter
#MNEM .UNIT           VALUE  : DESCRIPTION                    {FORMAT} | ASSOCIATION
 PDAT  .                  GL  : Permanent Data                 {S}
 APD   .F                5.0  : Above Permanent Data           {F}
 DREF  .                  KB  : Depth Reference (KB,DF,CB)     {S}
 EREF  .F             3680.0  : Elevation of Depth Reference   {F}
 RUN   .                   1  : Run Number                     {F}
 TDL   .F               5080  : Total Depth Logger             {F}
 TDD   .F                     : Total Depth Driller            {F}
 CSGL  .F                     : Casing Bottom Logger           {F}
 CSGD  .F                     : Casing Bottom Driller          {F}
 CSGS  .IN                    : Casing Size                    {F}
 CSGW  .LB                    : Casing Weight                  {F}
 BS    .IN                    : Bit Size                       {F}
 MUD   .                      : Mud type                       {S}
 MUDS  .                      : Mud Source                     {S}
 MUDD  .GM/CC                 : Mud Density                    {F}
 MUDV  .CC                    : Mud Viscosity (Funnel)         {F}
 FL    .LB/S                  : Fluid Loss                     {F}
 PH    .                      : PH                             {F}
 RM    .OHM-M                 : Resistivity of Mud             {F}
 RMT   .DEG-F                 : Temperature of Mud             {F}
 RMF   .OHM-M                 : Resistivity. of Mud Filtrate   {F}
 RMFT  .DEG-F                 : Temperature of Mud Filtrate    {F}
 RMC   .OHM-M                 : Resistivity of Mud Cake        {F}
 RMCT  .DEG-F                 : Temperature of Mud Cake        {F}
 TMAX  .DEG-F                 : Maximum Recorded Temp.         {F}
 TIMC  .DATE                  : Date/Time Circulation Stopped  {D/M/YYY}
 TIML  .DATE                  : Date/Time Logger Tagged Bottom {D/M/YYY}
 UNIT  .                      : Logging Unit Number            {S}
 BASE  .                      : Home Base of Logging Unit      {S}
 ENG   .                      : Recording Engineer             {S}
 WIT   .                      : Witnessed By                   {S}

~Curve
#MNEM .UNIT           VALUE  : DESCRIPTION                    {FORMAT} | ASSOCIATION
 DEPTH .FT                    : Curve #   1                    
 CILD  .MMHO-M                : Curve #   2                    
 CILM  .MMHO-M                : Curve #   3                    
 RLL3  .OHM-M                 : Curve #   4                    
 SP    .MV                    : Curve #   5                    
 RILD  .OHM-M                 : Curve #   6                    
 RILM  .OHM-M                 : Curve #   7                    
 DCAL  .IN                    : Curve #   8                    
 RHOB  .G/CC                  : Curve #   9                    
 RHOC  .G/CC                  : Curve #  10                    
 DPOR  .PU                    : Curve #  11                    
 CNLS  .PU                    : Curve #  12                    
 GR    .GAPI                  : Curve #  13                    
 RXORT .                      : Curve #  14                    
 SPC   .MV                    : Curve #  15                    
 DGA   .GM/CC                 : Curve #  16                    
 MI    .OHM-M                 : Curve #  17                    
 MN    .OHM-M                 : Curve #  18                    
 SPOR  .PU                    : Curve #  19                    
 DT    .USEC/FT               : Curve #  20                    

~Tops_Parameter
#MNEM .UNIT           VALUE  : DESCRIPTION                    {FORMAT} | ASSOCIATION
 IQKGS .                      : Profile Web App Saved Data Indicator {S}
 TOPS  .           GeoReport  : Formation Source               {S}
 TOPDR .           Log Depth  : Tops Depth Reference           {S}

~Tops_Definition
#MNEM .UNIT           VALUE  : DESCRIPTION                    {FORMAT} | ASSOCIATION
 KID   .                      : Primary Key for the Stratigraphic Unit {S}
 KEY   .                      : User Define Primary Key        {S}
 ID    .                      : Stratigraphic Unit ID          {S}
 TOPT  .F                     : Top Depth                      {F}
 TOPB  .F                     : Base Depth                     {F}
 RANK  .                      : Rank of Unit, i.e. (FORMATION, SYSTEM, etc) {S}
 LVL   .                      : Level of Confidence (GOLD, SILVER, COPPER...) {S}
 TOPN  .                      : Stratigraphic Unit Name        {S}
 EON   .                      : EON Age                        {S}
 ERA   .                      : ERA Age                        {S}
 SYS   .                      : System                         {S}
 SSYS  .                      : Subsystem                      {S}
 SSER  .                      : Subseries                      {S}
 STG   .                      : Stage                          {S}
 GRP   .                      : Group                          {S}
 FORM  .                      : Formation                      {S}

~Tops_Data | Tops_Definition 
# KID KEY ID TOPT TOPB RANK LVL TOPN EON ERA SYS SSYS SSER STG GRP FORM
 "-999.25","1101231125220","3313601000",4338.0,0.0,"FORMATION","Poor","Topeka Limestone","Phanerozoic","Paleozoic","Carboniferous","Pennsylvanian","Upper","Virgilian","Shawnee","Topeka Limestone"
 "-999.25","1101231125221","3313609000",4454.0,0.0,"FORMATION","Poor","Oread Limestone","Phanerozoic","Paleozoic","Carboniferous","Pennsylvanian","Upper","Virgilian","Shawnee","Oread Limestone"
 "-999.25","1101231125222","3317300000",4524.0,0.0,"GROUP","Poor","Lansing","Phanerozoic","Paleozoic","Carboniferous","Pennsylvanian","Upper","Missourian","Lansing","-999.25"
 "110123112645","110123112645","-999.25",4583.0,4583.0,"BED","Poor","'D' Zone","-999.25","-999.25","-999.25","-999.25","-999.25","-999.25","-999.25","-999.25"
 "110123112711","110123112711","-999.25",4640.0,4640.0,"BED","Poor","'G' Zone","-999.25","-999.25","-999.25","-999.25","-999.25","-999.25","-999.25","-999.25"
 "110123112730","110123112730","-999.25",4684.0,4684.0,"BED","Poor","'H' Zone","-999.25","-999.25","-999.25","-999.25","-999.25","-999.25","-999.25","-999.25"
 "-999.25","1101231125223","3317500000",4716.0,0.0,"GROUP","Poor","Kansas City","Phanerozoic","Paleozoic","Carboniferous","Pennsylvanian","Upper","Missourian","Kansas City","-999.25"
 "110123112755","110123112755","-999.25",4790.0,4790.0,"BED","Poor","'K' Zone","-999.25","-999.25","-999.25","-999.25","-999.25","-999.25","-999.25","-999.25"
 "110123112818","110123112818","-999.25",4819.0,4819.0,"-999.25","Poor","'L' Zone","-999.25","-999.25","-999.25","-999.25","-999.25","-999.25","-999.25","-999.25"
 "110123112842","110123112842","-999.25",4840.0,4840.0,"BED","Poor","'M' Zone","-999.25","-999.25","-999.25","-999.25","-999.25","-999.25","-999.25","-999.25"
 "110123112903","110123112903","-999.25",4850.0,4850.0,"MEMBER","Poor","B KC","-999.25","-999.25","-999.25","-999.25","-999.25","-999.25","-999.25","-999.25"
 "-999.25","1101231125224","3323300000",4909.0,0.0,"GROUP","Poor","Marmaton","Phanerozoic","Paleozoic","Carboniferous","Pennsylvanian","Middle","Desmoinesian","Marmaton","-999.25"

~IQ_Control_Parameter
#MNEM   .UNIT                    VALUE  : DESCRIPTION                    {FORMAT} | ASSOCIATION
 IQKGS   .                               : Profile Web App Saved Data Indicator {S}
 IQSTRT  .F                      4195.0  : Starting Display Depth         {F}
 IQSTOP  .F                      5042.0  : Ending Display Depth           {F}
 IQSCLE  .FT/IN                     100  : Plot Scale Feet/Inch           {F}
 IQGRP   .                          ALL  : LAS, ROCK or HORIZON           {S}
 IQORDR  .                      DEFAULT  : DEFAULT or MODIFIED            {S}
 IQSHMIN .API                       0.0  : Gamma Ray Minimum Value (Default) {F}
 IQSHLY  .API                      60.0  : Gamma Ray Shaly Value (Default) {F}
 IQSH    .API                      70.0  : Gamma Ray Shale Value (Default) {F}
 IQSHHOT .API                     100.0  : Gamma Ray Hot Shale Value (Default) {F}
 IQSHMAX .API                     150.0  : Gamma Ray Maximum Value (Default) {F}
 IQTHN   .                         NPHI  : Thin Porosity Track Curve Mnemonic {S}
 IQOHM   .                          ILD  : Deep Induction Resistivity     {S}
 IQOHM_L .MMHO/M    -1.0007505629221916  : Conductivity Image Track Minimum Value {F}
 IQOHM_U .MMHO/M     476.19047619047615  : Conductivity Image Track Maximum Value {F}
 IQPHI   .                         NPHI  : Neutron porosity               {S}
 IQPHI_L .PU                    -0.0050  : Porosity Image Track Minimum Value {F}
 IQPHI_U .PU                      1.756  : Porosity Image Track Maximum Value {F}
 GRNL    .%                         0.0  : % GR Count Lower Limit         {F}
 GRNU    .%                       100.0  : % GR Count Upper Limit         {F}
 GRL     .API                       0.0  : GR (API) Lower Limit           {F}
 GRU     .API                     150.0  : GR (API) Upper Limit           {F}
 NEUTL   .%                         0.0  : % Neutron Count Upper PHI Limit {F}
 NEUTU   .%                       100.0  : % Neutron Count Lower PHI Limit {F}
 NPHIL   .PU                       0.01  : Neutron Porosity Lower Limit   {F}
 NPHIU   .PU                        0.4  : Neutron Porosity Upper Limit   {F}

~IQ_Control_Definition
#MNEM   .UNIT           VALUE  : DESCRIPTION                    {FORMAT} | ASSOCIATION
 IQ_SRC  .                      : Data Source (LAS, TOPS, ROCK)  {S}
 IQ_TYPE .                      : Type of Track Data             {S}
 IQ_DESC .                      : Track Description              {S}

~IQ_Control_Data | IQ_Control_Definition 
# IQ_SRC IQ_TYPE IQ_DESC
 "LAS","LITH","Lithology - Gamma Ray"
 "LAS","LAS","LAS - Reference - GR,SP,CAL Logs"
 "LAS","LAS","LAS - Induction Resistivity Logs"
 "LAS","LAS","LAS - Litho-Density - NPHI,RHOB,PE Logs"
 "LAS","LITH","Colorlith - Rhomaa-NPHI Track"
 "LAS","ROCK","Lithology - Rhomaa-NPHI Track"
 "LAS","PHI","Thin Porosity Track"
 "LAS","LITH","Colorlith - Porosity Imager Nonlinear"
 "LAS","GRAIN","Texture - by Gamma Ray"
 "LAS","LITH","Colorlith - Resistivity Imager Nonlinear"
 "TOPS","STRAT","Horizons - Stratigraphic Units"
 "ROCK","ROCK","Lithology - Rock Column"
 "ROCK","PHI","Porosity Type"
 "ROCK","GRAIN","Texture - by User Input"
 "ROCK","ICON","Sedimentary Structures"
 "ROCK","ICON","Fossils"
 "ROCK","COLOR","Color - Rock RGB Values"
 "ROCK","DESC","Description"

~IQ_Geo_Report_Parameter
#MNEM   .UNIT                 VALUE  : DESCRIPTION                    {FORMAT} | ASSOCIATION
 IQKGS   .                       YES  : Profile Web App Saved Data Indicator {S}
 GEOSTRT .F                   4200.0  : Starting Display Depth         {F}
 GEOSTOP .F                   5028.0  : Ending Display Depth           {F}
 GEOSRC  .          Geologist Report  : Source                         {S}
 GEOREF  .                 Log Depth  : Depth Reference                {S}

~IQ_Geo_Report_Definition
#MNEM   .UNIT           VALUE  : DESCRIPTION                    {FORMAT} | ASSOCIATION
 GEOTOP  .F                     : Remarks/Comments/Notes Top Depth {F}
 GEOBASE .F                     : Remarks/Comments/Notes Bottom Depth {F}
 GEOBED  .F                     : Bed Thickness                  {F}
 GEODES  .                      : DESCRIPTION                    {S}

~IQ_Geo_Report_Data | IQ_Geo_Report_Definition 
# GEOTOP GEOBASE GEOBED GEODES
 4200.0,4204.0,4.0,"4200; 4204; SH: dk gry, m.sft-m.hrd.dns.hack. "
 4204.0,4210.0,6.0,"4204; 4210; LS: crm,m.sft.,dns.mxln.,occ.foss. N phi NSFOC "
 4210.0,4216.0,6.0,"4210; 4216; SH: kd.gry-blk.,m.sft-m.hrd.,dns.,earth,occ.sndy "
 4216.0,4220.0,4.0,"4216; 4220; LS: crm,m.sft.,dns.mxln.,occ.foss. N phi NSFOC "
 4220.0,4236.0,16.0,"4220; 4236; SH: dk.gry-blk.,m.sft-m.hrd.dns.,occ.sndy "
 4236.0,4240.0,4.0,"4236; 4240; LS: crm.,m.sft-m.hrd.,dns.,foss.-occ.foss.,sndy.mxln-cmt. N phi NSFOC "
 4240.0,4241.0,1.0,"4240; 4241; SH: dk.gry-blk.,sft-m.sft.,dns.,earth-fiss. "
 4241.0,4244.0,3.0,"4241; 4244; LS: crm-wh.,m.sft.,Vfxln...tr.vf g. intxln phi NSFOC "
 4244.0,4254.0,10.0,"4244; 4254; SH: dk.gry-blk.,sft-m.sft.,dns.,earth-fiss. "
 4254.0,4258.0,4.0,"4254; 4258; LS: crm,m.sft.,dns.,foss.,VFxln. N phi NSFOC "
 4258.0,4266.0,8.0,"4258; 4266; SH: dk.gry.-blk.,m.sft,dns.earthy-hack. "
 4266.0,4270.0,4.0,"4266; 4270; LS: crm-wh.,m.hrd.,dns.VFXLN.,foss-det. N phi NSFOC "
 4270.0,4280.0,10.0,"4270; 4280; SH: dk.gry.,m.sft.,dns,hack-fiss. "
 4280.0,4284.0,4.0,"4280; 4284; LS: crm.,m.sft.,det.,occ.ool. w / vfxln.mat.blk.oil stn.in v-pr.intpart & pp.vug phi,fr-gd,cut of phi w/ show "
 4284.0,4296.0,12.0,"4284; 4296; SH: dk.gry.,m.sft.,dns.,hack pyr. "
 4296.0,4302.0,6.0,"4296; 4302; LS: wh-crm.,m.sft-m.hrd.,dns.foss.+ool.,fr.cht. N phi NSFOC "
 4302.0,4302.0,-999.25,"4302; 4302; SH: dk.gry.,m.sft.,dns.,hack pyr., occ.sandy "
 4302.0,4320.0,18.0,"4302; 4320; SLT:lt.gry,v.sft.v.clay no vis phi NSFOC "
 4320.0,4324.0,4.0,"4320; 4324; SLT:lt.gry,v.sft,tr.gry,hrd.,dns.,vf grain,pr srtd.,w/ cmt no vfs. phi NSFOC "
 4324.0,4338.0,14.0,"4324; 4338; SH: gry-dk.gry.,m.sft-m.hrd.dns.,hack. "
 4338.0,4352.0,14.0,"4338; 4352; LS: crm-wh,m.sft-m.hrd.,vfg - mxln.,occ.chlk.,occ.ool.w/ fr-gd.oom. phi w/ blk.asph.oil stn. 102 pc.fairly oil gd-ex.cut f ... perm "
 4352.0,4356.0,4.0,"4352; 4356; LS: crm-wh.,m.sft-m.hrd.,dns.mxln,occ.chlk.occ.pc.w/ gd. oom. phi NSFOC "
 4356.0,4361.0,5.0,"4356; 4361; SH: dk.gry.,m.sft.,dns.,hack.pyr. "
 4361.0,4370.0,9.0,"4361; 4370; LS: crm-wh.,sft.,chkl.to hrd. + cht. mx/ N N phi NSFOC "
 4370.0,4372.0,2.0,"4370; 4372; LS.crm-wh-lt.gry.,sft-hrd,chlk.,occ.ool + foss. N phi NSFOC "
 4372.0,4380.0,8.0,"4372; 4380; SH: dk.gry-gry grn.,m.sft.,dns.hack.,pyr "
 4380.0,4390.0,10.0,"4380; 4390; LS: crm.,sft.,vfg-mx/N, occ chlk occ.fr-vfg pp, vug phi-oom phi fr.int. ool phi 1-2 pc.w/ blk.stn.,wk-fr.cmt _f / v ? perm. v.wk.show "
 4390.0,4394.0,4.0,"4390; 4394; LS: crm.,sft.,A.A det.w/fr.pr phi int.dark blk.stn,fr-wk cut + f/ AA. abun chrtyls. "
 4394.0,4410.0,16.0,"4394; 4410; SH: dk.gry-blk.,m.sft-m.hrd.dns.,occ.calcareous,occ.sndy.occ.foss.hack-earth.,pyr. "
 4410.0,4420.0,10.0,"4410; 4420; SH: dk.gry-blk.,m.hrd-m.sft.dns.,occ.snd.,calc, + foss.pyr.,hack-earth. "
 4420.0,4430.0,10.0,"4420; 4430; LS: crm-lt-gry.,m.sft-m.hrd.,mxln.occ.mic.,occ.chlk.occ.foss.+ool. n phi NSFOC "
 4430.0,4438.0,8.0,"4430; 4438; LS: crm-lt.gry.,m.sft-m.hrd.,dns.,mxln,occ.chlk,tr.mic occ.foss. + ool. N phi NSFOC "
 4438.0,4454.0,16.0,"4438; 4454; SH: dk.gry.,m.sft.,dns.,hack.occ.sndy,occ.slt; lt.gry,sft,earth.dns. no vis phi NSFOC "
 4454.0,4470.0,16.0,"4454; 4470; LS: wh-crm.,sft-m.sft.,vfg-mxln.,chlk.occ.foss.,ool,w/ pr.oom phi + pr.vfg intxln phi blk.stn in oom. phi. intxln phi barren +/- 50% live tarry oil 50% asph.oil.v? perm. v.wk.show "
 4470.0,4474.0,4.0,"4470; 4474; LS: wh-crm AA occ.vfxln,dns.,hrd. "
 4474.0,4476.0,2.0,"4474; 4476; SH: gry-dk.gry,m.hrd.dns.sndy.hack N phi NSFOC "
 4476.0,4486.0,10.0,"4476; 4486; LS: crm-lt.gry.,sft+chrty-hrd_mic.,mxln.occ.foss. + ool. N phi NSFOC "
 4486.0,4490.0,4.0,"4486; 4490; SH: gry-dk.gry,m.hrd,dns.,sndy. "
 4490.0,4502.0,12.0,"4490; 4502; SS: -slt: gry-lt.gry,m.sft,vfg.,v.pr.srtd.fn.grn.,mod.rnd. no vis phi NSFOC "
 4502.0,4514.0,12.0,"4502; 4514; SH: dk.gry,m.sft,dns.,slty-sndy,hack.,occ.ss::..,m.sft-hrd.vfg-fn.m.srtd.,rnd.ang.,w. cmtd. part. n phi NSFOC "
 4514.0,4524.0,10.0,"4514; 4524; SH: dk.gry,m.sft,dns,ss:-slt: AA.sft.carb.part.n phi NSFOC "
 4524.0,4534.0,10.0,"4524; 4534; LS: crm.,sft-hrd.,dns.,vfg mxln.,occ.chlk.,occ ool. w/ tr. int ool phi _ pr pp.,vug phi - tr intxln phi,fr.unif.brn.oil stn. ad-ex.cut _ fl.v. ? perm "
 4534.0,4540.0,6.0,"4534; 4540; LS: AA tan,hrd,dns.mic.n phi NSFOC "
 4540.0,4556.0,16.0,"4540; 4556; LS: crm-tan.,hrd-m.hrd.dns.mxln-mic "
 4556.0,4560.0,4.0,"4556; 4560; SH: lt-dk.gry.,m.sft.,dns.,hack "
 4560.0,4570.0,10.0,"4560; 4570; SH: lt-dk.gry,m.sft.,dns.hack,earth.,slty.,occ.sndy "
 4570.0,4583.0,13.0,"4570; 4583; SH: dk.gry-blk.,m.sft,dns.,hack.,calc.,pyr.,occ.sndy tr.SS: wh.,hrd.,m-fn.grn,... w.rnd. no vis phi NSFOC "
 4583.0,4600.0,17.0,"4583; 4600; LS: wh.,sft-m.hrd.,vfg-mxln.,occ.chrty.,occ.tr pp-fr.vug phi, w/ blk.oil stn.,gd-ex.cut _fl. v ? perm v.weak show "
 4600.0,4604.0,4.0,"4600; 4604; LS: wh.,sft-m.hrd.,vfg-mxln.,occ.chrty.,occ.tr pp-fr.vug phi w/ blk.oil stn.,gd-ex. cut + fl.v. ? perm v. weak show "
 4604.0,4608.0,4.0,"4604; 4608; SH: dk.gry.,m.sft,dns.lam.hack. "
 4608.0,4614.0,6.0,"4608; 4614; LS: "
 4614.0,4622.0,8.0,"4614; 4622; SH: dk.gry.,m.sft,dns.lam.hack. "
 4622.0,4630.0,8.0,"4622; 4630; SH: lt-dk.gry.,m.sft.,dns.hack.occ.slty "
 4630.0,4640.0,10.0,"4630; 4640; SH: lt-dk.gry.,m.sft.,dns.,hack.,slty. "
 4640.0,4650.0,10.0,"4640; 4650; LS: crm-wh.,m.hrd-sft.,dns.vfg-mxln.,occ,chlk.,tr.v.pr.vug.phi w/ oil stn,gd.cut + fl.v ? perm v.weak show "
 4650.0,4660.0,10.0,"4650; 4660; LS: crm,sft,vfg.-mxln.,dns.chlk N phi NSFOC "
 4660.0,4670.0,10.0,"4660; 4670; LS: crm-tan,m.sft-m.hrd.dns.,mxln,occ.chlk n phi NSFOC "
 4670.0,4672.0,2.0,"4670; 4672; SH: dk.gry-blk,m.sft.dns.hack-earth.occ.carb. "
 4672.0,4684.0,12.0,"4672; 4684; SH: lt.gry.,sft,sndy.,earth dns,hack-fiss "
 4684.0,4692.0,8.0,"4684; 4692; LS: crm-lt.gry.,m.hrd.,dns.fnxln-mxln.foss. n phi NSFOC "
 4692.0,4704.0,12.0,"4692; 4704; LS: crm-wh.,hrd-m.sft.,dns,fnxln-mxln foss. N phi NSFOC "
 4704.0,4716.0,12.0,"4704; 4716; SH: dk.gry.,m.sft.,dns.hack.pyr.tr.ss;wh.,m.hrd.,vfg.,ang.,pr srtd.,mica w/ blk.asph.oil specks. pr. phi "
 4716.0,4734.0,18.0,"4716; 4734; LS: crm-wh.,m.hrd.,dns.mxln-vfxln.,occ.chlk,pyr.,foss + ool.,tr.cht.,occ. pr. w. pr vug phi + vfg intxln phi mott-sat.stn.fr-gd.cut + fl. v. ? perm. "
 4734.0,4740.0,6.0,"4734; 4740; LS: crm-wh.,m.hrd.,dns.mxln-vfxln.,ool + vfxln,w/ fr.oom phi + lt.unif.oil stn. ? perm. "
 4740.0,4754.0,14.0,"4740; 4754; LS: crm-wh.,m.hrd.,dns.mxln-vfxln.,ool + vfxln.,ool.grainstone-packstone w/ gd.ex. int ool + ooc. leached moldic phi, lt-dk.brn unif stn.,occ.mott.,gd.cut + fl. "
 4754.0,4760.0,6.0,"4754; 4760; SH: gry-blk.,m.sft.,dns.earth-hack.,occ.sndy "
 4760.0,4762.0,2.0,"4760; 4762; Slt gry, sft.,clay-waxy. "
 4762.0,4774.0,12.0,"4762; 4774; SS: wh-lt.gry.,m.sft-hrd.dns.fn.grn.,med-w.srtd.,s.. ang.occ.fr.A,mod-v.smtd v ? phi sh. lam. NSFOC "
 4774.0,4790.0,16.0,"4774; 4790; SS: wh-lt.gry.,m.sft-hrd.dns.fn.grn.,med-w.srtd.,s.. ang.occ.fr.A,mod-v.smtd, occ. pyr.no vis.phi sh. lam. NSFOC "
 4790.0,4804.0,14.0,"4790; 4804; LS: crm-wh.,sft-m.hrd.,dns.,fnxln,chlk.,pyr.,1-2pc w/pr. vug phi + blk.stn.,fr-pr cut + fl. v ? perm. v. weak show N phi NSFOC "
 4804.0,4810.0,6.0,"4804; 4810; SH: gry-blk.,m.sft-m.hrd.,dns.slty-sndy,earthy "
 4810.0,4814.0,4.0,"4810; 4814; SH: gry-blk, occ.,lam. "
 4814.0,4819.0,5.0,"4814; 4819; Slt: gry-lt.gry.,sft,fr mica.no vis.phi NSFOC "
 4819.0,4829.0,10.0,"4819; 4829; LS: wh-crm.,sft-m.hrd.,mxln-vfxln.,occ.chrty.,pyr.,occ.foss 1-2 pc. w/ vfg pp phi + blk. oil stn.,gd.cut + fl. v. weak show "
 4829.0,4836.0,7.0,"4829; 4836; LS: wh-crm.,AA. mxln, hrdr "
 4836.0,4840.0,4.0,"4836; 4840; SH: gry-dk.gry.,m.sft-m.hrd.,dns.,hack "
 4840.0,4850.0,10.0,"4840; 4850; LS: crm,hrd,dns.,mxln,mic. N phi NSFOC "
 4850.0,4860.0,10.0,"4850; 4860; SH: gry-rd.brn.,m.hrd-sft,earth.-hack.,sndy "
 4860.0,4870.0,10.0,"4860; 4870; SH: AA.,predom rd.brn,sft,earthy, + sndy "
 4870.0,4892.0,22.0,"4870; 4892; SH: lt-dk.gry-rd.brn.,m.sft,dns.,sndy,earty tr. SS: gry,sft,vfg.,mod.srtd.,pr.cmtd.mod.rnd.,glauc. No r:s. phi NSFOC "
 4892.0,4909.0,17.0,"4892; 4909; SS: - slt gry.,m.sft-sft.,dns,vfg.mod.srtd.,pr.cmtd.,m.rnd.glauc. no vis phi NSFOC "
 4909.0,4924.0,15.0,"4909; 4924; LS: crm-lt.gry.,m.hrd-hrd.,vfg-mxln,dns,occ.foss. + ool. rare tr. pr. vug. + int ool. phi w/ mott.drk.stn. gd.cut + fl. v ? perm v.weak show "
 4924.0,4932.0,8.0,"4924; 4932; LS: crm-lt.gry,hrd,dns. ool + foss., fnxln n phi NSFOC "
 4932.0,4940.0,8.0,"4932; 4940; LS: crm-lt.gry hrd-m.hrd, dns, ool + foss.,fnxln-mxln. n phi NSFOC "
 4940.0,4950.0,10.0,"4940; 4950; SH: gry, m.sft _ m. hrd.,dns.sndy-earth.occ.slty. "
 4950.0,4964.0,14.0,"4950; 4964; LS: wh-tan,hrd.-m.sft.,dns.mxln-vfxln,mic.,occ.foss + ool,chrty,pyr "
 4964.0,4972.0,8.0,"4964; 4972; LS: tan,hrd,dns.,mxln.,mic.occ.cht. N phi NSFOC "
 4972.0,4980.0,8.0,"4972; 4980; LS: tan, occ. wh-crm, m.hrd.,fnxln,dns.foss. + ool N phi NSFOC "
 4980.0,4988.0,8.0,"4980; 4988; SH: lt.gry-blk.,m.sft,dns,occ.carb.,pyr.earthy occ. carbonate grns "
 4988.0,5000.0,12.0,"4988; 5000; LS: crm-lt.gry.,m.hrd.,dns,foss.,fnxln,occ.cht.+pyr. n phy NSFOC "
 5000.0,5009.0,9.0,"5000; 5009; LS: crm-lt.gry., less foss.,more mic. + cht. N phi NSFOC "
 5009.0,5011.0,2.0,"5009; 5011; SH: blk, m.hrd.,dns,carb.,earth,pyr. "
 5011.0,5020.0,9.0,"5011; 5020; LS: crm-tan,sft-hrd.,dns,mxln-occ.chlk.,occ.mic-chrty.,pyr.,occ.foss. N phi NSFOC "
 5020.0,5028.0,8.0,"5020; 5028; LS: crm-tan,m.hrd-hrd,mxln-vfxln.,foss, pyr. occ. cht.,occ.chlk N phi NSFOC "

~IQ_Las_Parameter
#MNEM .UNIT           VALUE  : DESCRIPTION                    {FORMAT} | ASSOCIATION
 DEPT  .FT          SELECTED  : Depth                          
 CILD  .MMHO/M      SELECTED  : Deep Induction Conductivity    
 CILM  .MMHO/M      SELECTED  : Medium Induction Conductivity  
 RLL3  .OHM-M       SELECTED  : Deep Laterolog Resistivity     
 SP    .MV          SELECTED  : Spontaneous Potential          
 RILD  .OHM-M       SELECTED  : Deep Induction Resistivity     
 RILM  .OHM-M       SELECTED  : Medium Induction Resistivity   
 DCAL  .IN          SELECTED  : Caliper                        
 RHOB  .GM/CC       SELECTED  : Bulk Density                   
 RHOC  .GM/CC       SELECTED  : Bulk Density Correction        
 DPOR  .PU          SELECTED  : Density porosity               
 CNLS  .PU          SELECTED  : Neutron porosity               
 GR    .API         SELECTED  : Gamma Ray                      
 RXORT .RATIO                 : Rxo/Rt ratio                   
 SPC   .MV                    : Spontaneous Potential          
 DGA   .GM/CC                 : Bulk Density                   
 MI    .OHM-M       SELECTED  : Micro Inverse Resistivity      
 MN    .OHM-M       SELECTED  : Micro Normal Resistivity       
 SPOR  .PU          SELECTED  : Sonic porosity                 
 DT    .USEC/FT     SELECTED  : Acoustic transit time          

~ASCII
# DEPTH CILD CILM RLL3 SP RILD RILM DCAL RHOB RHOC DPOR CNLS GR RXORT SPC DGA MI MN SPOR DT
 4195.000,181.621,155.302,8.378,-49.946,5.506,6.439,8.936,2.594,.054,.068,.127,83.376,-16.115,-9.228,2.876,15.462,8.130,.154,69.239
 4195.500,180.029,152.427,8.632,-50.730,5.555,6.561,8.735,2.580,.052,.076,.119,83.588,-15.849,-10.767,2.873,16.155,8.428,.151,68.887
 4196.000,179.561,148.978,8.800,-52.488,5.569,6.712,8.736,2.564,.049,.085,.112,85.831,-16.060,-12.562,2.889,16.248,8.376,.150,68.720
 4196.500,181.298,148.684,8.517,-54.479,5.516,6.726,8.735,2.553,.048,.092,.106,84.387,-16.159,-14.590,2.878,16.046,8.304,.150,68.782
 4197.000,183.977,150.955,8.162,-56.642,5.436,6.624,8.735,2.546,.048,.096,.102,81.633,-16.098,-16.790,2.858,16.777,8.428,.152,69.007
 4197.500,187.139,154.875,7.838,-58.850,5.344,6.457,8.740,2.537,.047,.101,.102,73.761,-16.328,-19.036,2.753,17.984,8.471,.154,69.234
 4198.000,191.161,159.625,7.518,-60.906,5.231,6.265,8.736,2.527,.045,.107,.105,71.156,-17.475,-21.129,2.744,20.955,9.022,.155,69.381
 4198.500,195.958,164.305,8.007,-62.551,5.103,6.086,8.716,2.520,.043,.111,.107,73.854,-19.597,-22.811,2.755,27.563,10.869,.155,69.500
 4199.000,200.684,168.264,9.252,-63.529,4.983,5.943,8.700,2.520,.044,.111,.106,79.917,-21.953,-23.826,2.838,32.232,12.186,.156,69.608
 4199.500,205.221,171.561,9.623,-63.671,4.873,5.829,8.702,2.527,.045,.107,.104,79.514,-23.726,-24.005,2.832,29.983,11.480,.157,69.665
 4200.000,210.370,174.777,9.222,-62.991,4.753,5.722,8.698,2.536,.047,.102,.106,75.621,-24.558,-23.363,2.776,24.925,10.333,.158,69.884
 4200.500,218.598,179.495,8.858,-61.726,4.575,5.571,8.707,2.547,.048,.096,.119,79.082,-24.736,-22.134,2.825,20.505,9.734,.165,70.860
 4201.000,230.767,188.529,8.567,-60.300,4.333,5.304,8.703,2.556,.050,.090,.147,82.429,-24.355,-20.746,2.864,17.620,8.948,.179,72.883
 4201.500,241.486,203.407,7.736,-59.200,4.141,4.916,8.700,2.563,.054,.086,.187,91.180,-22.671,-19.683,2.929,13.359,7.106,.196,75.177
 4202.000,246.857,220.744,6.195,-58.802,4.051,4.530,8.691,2.568,.057,.083,.221,104.380,-20.135,-19.322,3.000,9.874,5.477,.204,76.398
 4202.500,243.320,232.871,5.249,-59.233,4.110,4.294,8.636,2.574,.060,.079,.235,109.635,-19.044,-19.791,3.000,9.215,5.106,.199,75.687
 4203.000,228.651,232.900,5.076,-60.344,4.373,4.294,8.598,2.586,.061,.073,.222,93.322,-23.051,-20.938,2.946,9.999,5.480,.179,72.848
 4203.500,210.697,217.820,5.670,-61.798,4.746,4.591,8.592,2.601,.058,.064,.163,75.793,-33.998,-22.430,2.851,15.950,7.732,.148,68.442
 4204.000,197.377,189.618,9.173,-63.239,5.067,5.274,8.596,2.613,.053,.057,.115,66.174,-48.450,-23.907,2.788,34.501,15.339,.115,63.721
 4204.500,183.279,155.370,23.178,-64.407,5.456,6.436,8.598,2.616,.045,.055,.083,49.125,-60.102,-25.113,2.747,63.259,26.816,.087,59.773
 4205.000,164.950,123.100,46.009,-65.173,6.062,8.123,8.594,2.612,.040,.058,.063,41.272,-65.335,-25.916,2.718,75.704,31.013,.069,57.233
 4205.500,144.761,97.260,50.137,-65.485,6.908,10.282,8.599,2.605,.040,.061,.053,43.058,-63.719,-26.265,2.707,66.408,27.954,.063,56.408
 4206.000,122.465,78.288,36.084,-65.302,8.166,12.773,8.637,2.603,.046,.062,.051,51.568,-55.487,-26.119,2.708,62.145,25.969,.067,56.959
 4206.500,101.251,65.337,25.669,-64.573,9.877,15.305,8.652,2.606,.056,.061,.053,60.749,-42.917,-25.427,2.715,61.162,24.905,.075,58.059
 4207.000,86.559,58.216,21.145,-63.258,11.553,17.177,8.646,2.609,.065,.059,.057,67.358,-30.523,-24.149,2.727,56.388,23.605,.082,59.162
 4207.500,83.851,57.407,20.316,-61.371,11.926,17.419,8.644,2.609,.069,.059,.064,76.837,-23.485,-22.299,2.793,50.918,20.990,.093,60.614
 4208.000,95.185,64.715,21.317,-59.021,10.506,15.452,8.657,2.604,.068,.062,.077,90.291,-22.810,-19.987,2.923,49.409,18.538,.111,63.224
 4208.500,117.185,83.328,18.818,-56.417,8.533,12.001,8.719,2.600,.065,.064,.097,107.613,-23.899,-17.420,3.000,39.471,14.896,.139,67.187
 4209.000,146.592,113.935,10.882,-53.826,6.822,8.777,8.810,2.599,.063,.065,.119,119.469,-23.131,-14.866,3.000,19.447,8.566,.172,71.857
 4209.500,176.953,151.488,5.963,-51.505,5.651,6.601,8.839,2.598,.061,.066,.149,128.112,-19.152,-12.582,3.000,10.207,5.529,.202,76.142
 4210.000,205.353,188.242,5.027,-49.635,4.870,5.312,8.832,2.593,.059,.068,.191,126.663,-14.397,-10.749,3.000,8.649,4.890,.223,79.035
 4210.500,231.809,218.472,5.078,-48.286,4.314,4.577,8.830,2.586,.056,.072,.220,120.606,-12.231,-9.438,3.000,8.850,4.899,.232,80.281
 4211.000,257.179,240.381,5.252,-47.439,3.888,4.160,8.835,2.580,.054,.076,.222,122.111,-13.687,-8.627,3.000,9.217,5.029,.232,80.298
 4211.500,279.031,254.333,5.358,-47.026,3.584,3.932,8.863,2.578,.053,.077,.219,117.027,-17.036,-8.252,3.000,9.306,5.080,.227,79.618
 4212.000,294.668,260.484,5.622,-46.976,3.394,3.839,8.878,2.580,.052,.076,.220,104.339,-20.479,-8.239,3.000,9.767,5.285,.220,78.628
 4212.500,302.419,259.390,6.063,-47.235,3.307,3.855,8.879,2.583,.051,.074,.216,98.521,-22.944,-8.535,2.988,10.649,5.609,.213,77.599
 4213.000,302.449,253.839,6.417,-47.768,3.306,3.940,8.851,2.584,.049,.074,.214,95.682,-23.823,-9.105,2.965,11.395,5.687,.207,76.844
 4213.500,298.947,248.448,6.563,-48.558,3.345,4.025,8.830,2.581,.047,.075,.222,99.748,-23.167,-9.932,2.998,11.808,5.634,.206,76.653
 4214.000,295.485,247.228,6.175,-49.608,3.384,4.045,8.826,2.579,.048,.077,.232,110.529,-21.364,-11.019,3.000,11.072,5.560,.209,77.071
 4214.500,292.753,251.850,5.346,-50.941,3.416,3.971,8.837,2.580,.052,.076,.234,112.307,-19.332,-12.389,3.000,9.943,5.318,.215,77.882
 4215.000,291.986,260.804,4.837,-52.574,3.425,3.834,8.837,2.584,.059,.073,.230,104.725,-19.801,-14.059,3.000,9.163,5.031,.219,78.462
 4215.500,291.007,269.289,4.618,-54.462,3.436,3.714,8.845,2.596,.066,.067,.224,100.447,-27.079,-15.985,3.000,8.983,4.951,.213,77.583
 4216.000,281.211,270.140,4.717,-56.441,3.556,3.702,8.837,2.618,.071,.054,.212,87.264,-42.180,-18.001,2.956,11.094,5.606,.189,74.187
 4216.500,262.850,256.080,6.410,-58.205,3.804,3.905,8.826,2.648,.072,.036,.176,58.668,-60.100,-19.802,2.870,24.577,10.547,.149,68.590
 4217.000,244.323,226.113,17.574,-59.391,4.093,4.423,8.833,2.673,.067,.022,.128,37.176,-75.274,-21.025,2.822,61.914,27.029,.106,62.497
 4217.500,231.215,190.060,51.604,-59.713,4.325,5.261,8.841,2.678,.058,.019,.097,27.596,-84.866,-21.385,2.794,93.413,47.794,.076,58.235
 4218.000,219.900,161.363,75.948,-59.094,4.548,6.197,8.876,2.660,.050,.029,.083,26.468,-86.921,-20.803,2.770,97.925,50.817,.071,57.538
 4218.500,207.585,146.824,49.564,-57.700,4.817,6.811,8.937,2.634,.047,.044,.085,33.656,-80.727,-19.446,2.756,77.669,33.931,.088,59.954
 4219.000,191.818,144.302,17.293,-55.881,5.213,6.930,9.008,2.610,.049,.059,.100,57.164,-66.529,-17.664,2.765,33.583,13.611,.112,63.322
 4219.500,184.734,148.855,7.187,-54.050,5.413,6.718,9.041,2.575,.055,.079,.126,74.197,-49.153,-15.870,2.792,14.183,6.803,.133,66.282
 4220.000,203.294,162.327,7.904,-52.556,4.919,6.160,9.243,2.516,.065,.114,.164,73.047,-36.656,-14.413,2.802,18.074,7.802,.159,69.956
 4220.500,248.973,194.109,10.184,-51.600,4.016,5.152,9.574,2.441,.087,.157,.208,76.328,-32.217,-13.495,2.827,17.382,7.412,.210,77.258
 4221.000,303.075,247.262,8.039,-51.209,3.299,4.044,9.708,2.379,.118,.193,.236,98.926,-31.828,-13.141,2.991,8.886,4.597,.293,89.025
 4221.500,338.536,306.723,4.480,-51.266,2.954,3.260,9.715,2.343,.147,.214,.249,132.753,-32.606,-13.235,3.000,4.475,2.786,.375,100.597
 4222.000,335.815,347.166,3.225,-51.580,2.978,2.881,9.663,2.339,.165,.217,.246,159.260,-37.288,-13.586,3.000,4.159,2.531,.402,104.366
 4222.500,312.755,349.969,3.947,-51.962,3.197,2.857,9.219,2.373,.166,.197,.218,168.887,-47.943,-14.005,3.000,12.548,5.894,.349,96.953
 4223.000,303.499,314.586,11.807,-52.267,3.295,3.179,9.018,2.440,.151,.158,.158,138.326,-61.298,-14.347,3.000,49.055,22.510,.245,82.182
 4223.500,304.962,261.343,30.792,-52.410,3.279,3.826,9.055,2.519,.123,.112,.117,94.207,-71.308,-14.527,2.953,85.516,42.256,.142,67.614
 4224.000,305.051,216.197,35.450,-52.355,3.278,4.625,9.069,2.574,.091,.079,.094,76.466,-74.380,-14.510,2.788,75.046,35.217,.086,59.658
 4224.500,296.215,190.616,21.833,-52.100,3.376,5.246,9.070,2.592,.066,.069,.086,77.224,-69.531,-14.292,2.799,45.797,19.422,.085,59.552
 4225.000,270.882,181.245,12.503,-51.680,3.692,5.517,9.111,2.588,.054,.071,.093,82.760,-56.812,-13.909,2.867,28.719,11.421,.116,63.907
 4225.500,233.792,181.422,7.869,-51.179,4.277,5.512,9.168,2.581,.050,.075,.112,83.985,-38.742,-13.444,2.875,16.405,7.209,.153,69.126
 4226.000,208.623,186.788,6.169,-50.729,4.793,5.354,9.212,2.570,.051,.082,.141,92.758,-22.329,-13.032,2.942,11.381,5.632,.183,73.448
 4226.500,201.048,194.411,5.779,-50.477,4.974,5.144,9.259,2.559,.053,.089,.181,110.948,-12.314,-12.817,3.000,10.573,5.337,.203,76.280
 4227.000,207.393,202.855,5.624,-50.513,4.822,4.930,9.286,2.553,.058,.092,.220,117.091,-9.081,-12.890,3.000,12.426,6.091,.212,77.526
 4227.500,222.537,211.628,5.713,-50.812,4.494,4.725,9.307,2.557,.064,.089,.235,111.733,-10.220,-13.226,3.000,13.221,6.337,.212,77.489
 4228.000,242.113,219.404,5.746,-51.232,4.130,4.558,9.327,2.568,.068,.083,.230,97.946,-13.225,-13.684,2.983,10.857,5.603,.208,76.877
 4228.500,257.791,224.944,5.787,-51.579,3.879,4.446,9.343,2.578,.070,.077,.217,90.706,-15.751,-14.068,2.928,10.659,5.488,.204,76.357
 4229.000,265.983,228.596,6.023,-51.699,3.760,4.374,9.341,2.585,.069,.073,.218,86.414,-16.873,-14.225,2.925,12.565,6.006,.203,76.219
 4229.500,271.168,231.947,5.992,-51.547,3.688,4.311,9.357,2.592,.068,.069,.236,85.368,-17.160,-14.110,2.954,12.113,5.970,.205,76.438
 4230.000,273.700,235.986,5.440,-51.186,3.654,4.238,9.383,2.599,.067,.065,.253,95.985,-16.952,-13.786,2.998,10.073,5.321,.206,76.706
 4230.500,274.841,239.307,5.107,-50.733,3.638,4.179,9.405,2.604,.068,.062,.260,105.854,-17.004,-13.370,3.000,9.241,4.995,.206,76.698
 4231.000,277.876,239.533,5.492,-50.291,3.599,4.175,9.404,2.603,.068,.063,.258,103.210,-18.048,-12.965,3.000,10.584,5.553,.204,76.368
 4231.500,284.778,237.334,6.147,-49.908,3.511,4.214,9.413,2.596,.064,.067,.251,97.836,-19.883,-12.619,2.993,12.354,6.238,.202,76.039
 4232.000,295.723,237.356,6.375,-49.580,3.382,4.213,9.403,2.584,.059,.074,.248,100.990,-21.667,-12.328,3.000,12.290,6.223,.204,76.324
 4232.500,308.789,243.590,6.113,-49.281,3.239,4.105,9.395,2.571,.056,.081,.252,110.075,-22.576,-12.067,3.000,11.286,5.818,.213,77.578
 4233.000,316.761,255.435,5.582,-48.998,3.157,3.915,9.406,2.560,.055,.088,.261,121.105,-21.810,-11.821,3.000,10.094,5.296,.225,79.299
 4233.500,318.958,268.701,4.970,-48.751,3.135,3.722,9.405,2.552,.057,.093,.262,129.288,-20.039,-11.611,3.000,8.774,4.719,.234,80.578
 4234.000,317.554,278.840,4.616,-48.588,3.149,3.586,9.413,2.543,.061,.098,.251,129.013,-18.478,-11.485,3.000,8.219,4.422,.236,80.913
 4234.500,314.747,283.698,4.662,-48.569,3.177,3.525,9.414,2.527,.062,.107,.242,117.543,-17.965,-11.504,3.000,8.434,4.530,.233,80.462
 4235.000,314.384,284.212,5.100,-48.726,3.181,3.519,9.397,2.488,.060,.130,.247,112.345,-18.803,-11.697,3.000,9.578,5.028,.234,80.593
 4235.500,316.083,282.333,5.662,-49.031,3.164,3.542,9.408,2.424,.057,.168,.262,112.701,-20.503,-12.039,3.000,10.285,5.324,.251,83.011
 4236.000,311.005,276.160,5.553,-49.391,3.215,3.621,9.514,2.362,.062,.204,.264,113.065,-22.186,-12.437,3.000,8.777,4.672,.275,86.460
 4236.500,290.668,258.420,4.847,-49.677,3.440,3.870,9.572,2.339,.075,.217,.247,112.240,-23.649,-12.760,3.000,7.029,4.048,.282,87.357
 4237.000,263.387,226.993,5.863,-49.782,3.797,4.405,9.247,2.370,.086,.199,.226,92.502,-26.057,-12.902,2.940,12.070,5.512,.258,84.021
 4237.500,236.345,191.927,9.197,-49.682,4.231,5.210,9.221,2.443,.088,.156,.187,63.782,-29.138,-12.839,2.768,19.516,7.713,.207,76.857
 4238.000,210.826,162.558,11.104,-49.465,4.743,6.152,9.209,2.532,.081,.104,.138,54.203,-31.511,-12.660,2.755,20.478,8.434,.147,68.355
 4238.500,190.535,138.947,12.302,-49.294,5.248,7.197,9.213,2.603,.073,.063,.108,56.547,-33.039,-12.525,2.769,25.956,9.750,.106,62.491
 4239.000,173.938,119.413,14.630,-49.331,5.749,8.374,9.217,2.623,.064,.051,.094,56.737,-33.268,-12.600,2.766,27.788,10.280,.090,60.240
 4239.500,162.858,107.257,15.033,-49.667,6.140,9.323,9.216,2.561,.053,.087,.091,58.445,-32.464,-12.972,2.730,24.542,9.836,.089,60.126
 4240.000,166.199,110.821,15.975,-50.282,6.017,9.024,9.233,2.412,.043,.174,.103,59.660,-32.405,-13.625,2.673,27.428,10.340,.108,62.814
 4240.500,188.321,138.492,15.778,-51.069,5.310,7.221,9.681,2.234,.046,.278,.138,65.764,-33.153,-14.449,2.685,23.674,8.625,.165,70.857
 4241.000,218.574,188.889,10.337,-51.888,4.575,5.294,10.416,2.102,.071,.355,.217,89.257,-31.650,-15.305,2.915,10.398,4.845,.256,83.661
 4241.500,236.205,244.466,4.999,-52.616,4.234,4.091,10.722,2.043,.106,.390,.273,108.865,-26.807,-16.070,3.000,3.996,3.062,.338,95.277
 4242.000,237.894,279.553,3.526,-53.183,4.203,3.577,10.607,2.049,.133,.386,.291,112.642,-25.213,-16.674,3.000,3.541,2.620,.362,98.659
 4242.500,231.767,277.206,4.167,-53.558,4.315,3.607,9.842,2.112,.145,.350,.262,99.141,-32.214,-17.087,2.993,6.142,3.130,.310,91.400
 4243.000,230.025,243.457,9.951,-53.723,4.347,4.108,9.170,2.221,.139,.286,.214,72.538,-43.834,-17.289,2.770,21.443,6.502,.214,77.740
 4243.500,239.510,204.063,24.635,-53.652,4.175,4.900,9.134,2.360,.123,.205,.162,49.340,-54.005,-17.255,2.687,44.198,12.229,.129,65.820
 4244.000,252.565,181.665,30.184,-53.327,3.959,5.505,9.284,2.486,.108,.131,.133,46.342,-58.310,-16.967,2.721,45.429,13.145,.100,61.617
 4244.500,248.241,178.187,16.055,-52.772,4.028,5.612,9.374,2.556,.101,.090,.121,63.224,-53.377,-16.449,2.761,24.493,8.099,.118,64.254
 4245.000,222.615,179.274,7.089,-52.067,4.492,5.578,9.072,2.579,.100,.077,.122,83.261,-40.396,-15.781,2.870,9.594,4.939,.151,68.820
 4245.500,192.437,173.478,6.511,-51.333,5.196,5.764,8.978,2.583,.095,.074,.141,92.128,-25.590,-15.084,2.937,10.928,5.834,.173,71.925
 4246.000,175.273,163.174,7.944,-50.679,5.705,6.128,8.966,2.586,.083,.072,.172,88.345,-16.399,-14.468,2.908,14.136,7.103,.180,72.905
 4246.500,173.436,156.717,8.717,-50.166,5.766,6.381,8.961,2.592,.070,.069,.193,83.947,-14.231,-13.992,2.896,15.241,7.499,.178,72.627
 4247.000,184.687,157.437,8.699,-49.794,5.415,6.352,8.942,2.600,.061,.064,.190,79.664,-16.218,-13.656,2.890,15.108,7.438,.174,72.172
 4247.500,201.014,163.164,8.318,-49.525,4.975,6.129,8.930,2.606,.057,.061,.176,77.201,-18.580,-13.425,2.873,14.208,7.306,.175,72.281
 4248.000,212.992,170.915,7.779,-49.326,4.695,5.851,8.938,2.612,.056,.057,.171,81.045,-19.084,-13.263,2.878,13.906,7.170,.181,73.151
 4248.500,217.242,178.973,7.088,-49.185,4.603,5.587,8.928,2.619,.059,.053,.177,93.406,-17.732,-13.159,2.947,12.802,6.591,.189,74.263
 4249.000,217.871,186.019,6.448,-49.116,4.590,5.376,8.926,2.627,.063,.049,.189,96.622,-16.052,-13.128,2.972,11.380,5.890,.193,74.846
 4249.500,218.068,190.579,6.342,-49.140,4.586,5.247,8.910,2.632,.067,.046,.206,91.315,-15.172,-13.189,2.944,11.571,5.838,.191,74.593
 4250.000,219.816,192.273,6.664,-49.264,4.549,5.201,8.901,2.632,.068,.046,.221,88.961,-15.509,-13.350,2.975,12.639,6.126,.186,73.776
 4250.500,222.726,192.266,6.962,-49.486,4.490,5.201,8.890,2.631,.068,.046,.224,86.994,-16.627,-13.609,2.980,13.413,6.210,.179,72.771
 4251.000,224.361,191.574,7.075,-49.808,4.457,5.220,8.893,2.632,.066,.046,.219,86.365,-17.759,-13.968,2.971,13.646,6.288,.172,71.790
 4251.500,221.731,189.475,7.058,-50.272,4.510,5.278,8.900,2.638,.064,.042,.210,91.229,-18.483,-14.469,2.961,13.077,6.312,.165,70.863
 4252.000,212.726,183.998,7.185,-50.974,4.701,5.435,8.902,2.649,.062,.036,.185,90.100,-19.147,-15.209,2.931,13.110,6.366,.157,69.784
 4252.500,198.413,173.844,7.475,-52.063,5.040,5.752,8.898,2.663,.061,.028,.150,92.250,-21.310,-16.335,2.938,13.911,6.698,.146,68.175
 4253.000,180.459,159.067,8.105,-53.695,5.541,6.287,8.891,2.673,.061,.022,.125,88.812,-26.570,-18.003,2.911,15.576,7.285,.129,65.805
 4253.500,159.065,139.748,9.577,-55.972,6.287,7.156,8.899,2.672,.059,.022,.114,69.460,-34.210,-20.318,2.835,20.716,8.627,.109,62.881
 4254.000,139.631,116.732,15.536,-58.889,7.162,8.567,8.895,2.658,.055,.031,.111,50.722,-42.411,-23.272,2.804,37.058,12.625,.088,60.006
 4254.500,127.446,93.956,31.229,-62.296,7.846,10.643,8.897,2.639,.052,.042,.104,44.962,-49.721,-26.716,2.782,63.167,18.935,.073,57.864
 4255.000,119.790,76.137,44.293,-65.920,8.348,13.134,8.894,2.626,.053,.049,.093,42.615,-53.977,-30.377,2.762,79.861,24.559,.066,56.849
 4255.500,109.561,64.870,43.459,-69.409,9.127,15.415,8.901,2.619,.056,.053,.086,43.927,-52.602,-33.903,2.750,88.755,28.520,.067,56.938
 4256.000,98.715,59.589,35.192,-72.392,10.130,16.782,8.899,2.608,.056,.060,.087,47.545,-46.782,-36.924,2.744,88.130,29.124,.073,57.887
 4256.500,92.887,59.970,27.623,-74.520,10.766,16.675,8.907,2.584,.054,.074,.097,49.680,-40.192,-39.089,2.740,61.825,21.573,.084,59.369
 4257.000,95.441,65.954,24.721,-75.494,10.478,15.162,8.901,2.555,.052,.091,.113,57.081,-36.089,-40.100,2.747,27.059,12.819,.096,61.021
 4257.500,103.994,76.079,22.590,-75.094,9.616,13.144,8.900,2.538,.053,.101,.129,68.107,-34.175,-39.737,2.764,12.501,9.698,.107,62.587
 4258.000,114.706,87.977,20.835,-73.238,8.718,11.367,8.932,2.541,.056,.099,.135,70.398,-32.433,-37.918,2.777,15.440,11.567,.117,63.990
 4258.500,129.465,102.094,18.446,-70.035,7.724,9.795,8.949,2.560,.060,.088,.135,69.416,-30.510,-34.752,2.784,28.685,15.658,.126,65.317
 4259.000,146.836,120.614,12.968,-65.816,6.810,8.291,8.982,2.580,.061,.076,.136,73.133,-27.268,-30.571,2.802,31.133,13.823,.137,66.887
 4259.500,164.339,141.856,8.261,-61.074,6.085,7.049,9.003,2.589,.060,.071,.146,86.239,-22.556,-25.865,2.892,19.584,8.807,.152,69.064
 4260.000,180.640,161.465,7.267,-56.350,5.536,6.193,9.052,2.588,.057,.072,.169,98.972,-17.671,-21.178,2.991,14.677,7.257,.172,71.772
 4260.500,196.526,177.701,6.887,-52.115,5.088,5.627,9.155,2.583,.056,.074,.203,105.562,-14.343,-16.980,3.000,12.423,6.450,.191,74.498
 4261.000,208.802,190.294,6.140,-48.686,4.789,5.255,9.215,2.582,.057,.075,.219,115.350,-12.531,-13.589,3.000,10.699,5.692,.206,76.619
 4261.500,216.500,198.224,5.658,-46.210,4.619,5.045,9.218,2.586,.058,.072,.215,121.082,-12.017,-11.149,3.000,10.244,5.454,.213,77.577
 4262.000,221.337,201.189,5.743,-44.680,4.518,4.970,9.214,2.593,.058,.069,.202,112.064,-12.800,-9.657,3.000,11.216,5.824,.210,77.263
 4262.500,226.133,200.933,6.459,-43.980,4.422,4.977,9.213,2.599,.060,.065,.192,100.007,-14.615,-8.994,3.000,13.042,6.532,.203,76.218
 4263.000,232.653,200.853,7.190,-43.918,4.298,4.979,9.211,2.601,.061,.064,.190,89.663,-16.687,-8.970,2.918,13.578,6.798,.197,75.362
 4263.500,239.101,203.434,7.099,-44.282,4.182,4.916,9.211,2.599,.063,.065,.187,86.495,-18.053,-9.370,2.900,12.492,6.401,.197,75.445
 4264.000,240.776,207.919,6.458,-44.894,4.153,4.810,9.212,2.592,.063,.069,.179,95.429,-18.501,-10.020,2.963,11.343,5.890,.204,76.398
 4264.500,235.957,210.791,5.952,-45.672,4.238,4.744,9.216,2.587,.063,.072,.178,102.898,-19.774,-10.834,3.000,11.045,5.722,.210,77.226
 4265.000,225.886,207.799,5.733,-46.633,4.427,4.812,9.209,2.589,.062,.071,.185,104.228,-24.209,-11.833,3.000,11.081,5.672,.205,76.512
 4265.500,212.058,195.992,6.698,-47.861,4.716,5.102,9.217,2.597,.061,.066,.186,100.761,-31.388,-13.099,3.000,12.662,6.043,.183,73.417
 4266.000,200.152,176.059,13.177,-49.417,4.996,5.680,9.223,2.608,.059,.060,.170,91.367,-38.817,-14.692,2.931,25.910,9.161,.149,68.633
 4266.500,193.350,154.038,22.489,-51.250,5.172,6.492,9.251,2.618,.058,.054,.149,72.645,-43.921,-16.562,2.841,55.637,15.616,.116,63.891
 4267.000,193.307,139.135,21.824,-53.159,5.173,7.187,9.267,2.614,.058,.056,.134,51.393,-45.635,-18.508,2.801,67.502,18.756,.095,60.877
 4267.500,196.661,137.592,16.550,-54.829,5.085,7.268,9.313,2.570,.054,.082,.130,41.927,-43.307,-20.215,2.764,53.938,15.932,.094,60.796
 4268.000,200.095,149.208,12.064,-55.929,4.998,6.702,9.394,2.467,.047,.142,.143,45.303,-37.226,-21.352,2.719,32.991,11.792,.119,64.375
 4268.500,206.215,170.850,9.189,-56.230,4.849,5.853,9.597,2.340,.047,.216,.179,54.120,-29.390,-21.690,2.699,21.714,9.304,.167,71.176
 4269.000,214.959,198.615,7.113,-55.694,4.652,5.035,10.041,2.251,.062,.268,.226,64.968,-21.614,-21.191,2.722,13.799,6.277,.218,78.386
 4269.500,222.377,223.701,4.908,-54.477,4.497,4.470,10.195,2.230,.083,.281,.242,83.487,-15.540,-20.011,2.895,5.551,3.748,.250,82.911
 4270.000,228.741,234.235,4.257,-52.870,4.372,4.269,9.668,2.268,.097,.258,.241,103.697,-13.600,-18.441,3.000,5.131,3.760,.253,83.335
 4270.500,234.217,227.318,5.751,-51.191,4.269,4.399,9.483,2.346,.096,.213,.237,103.044,-16.000,-16.799,3.000,9.033,5.243,.228,79.724
 4271.000,239.866,212.753,7.822,-49.690,4.169,4.700,9.465,2.439,.084,.158,.222,88.543,-20.386,-15.336,2.911,13.904,6.864,.193,74.802
 4271.500,246.633,201.069,8.534,-48.507,4.055,4.973,9.470,2.517,.070,.113,.187,84.344,-24.277,-14.190,2.878,16.325,7.847,.172,71.773
 4272.000,249.828,194.478,8.310,-47.669,4.003,5.142,9.468,2.562,.059,.086,.158,91.127,-25.858,-13.389,2.929,15.532,7.778,.166,71.040
 4272.500,242.214,189.889,7.794,-47.123,4.129,5.266,9.468,2.584,.053,.074,.150,91.012,-24.198,-12.880,2.928,13.878,7.426,.169,71.461
 4273.000,230.089,185.102,7.283,-46.770,4.346,5.402,9.469,2.595,.051,.067,.159,89.921,-20.954,-12.564,2.920,13.251,7.164,.174,72.181
 4273.500,221.541,180.714,6.976,-46.493,4.514,5.534,9.467,2.602,.051,.063,.172,89.423,-18.188,-12.325,2.916,13.156,6.959,.179,72.822
 4274.000,219.882,178.231,6.813,-46.190,4.548,5.611,9.467,2.604,.051,.062,.180,91.475,-16.945,-12.059,2.932,13.007,6.799,.182,73.295
 4274.500,229.462,178.974,6.893,-45.798,4.358,5.587,9.468,2.603,.051,.062,.187,99.736,-17.905,-11.704,2.998,13.019,6.787,.186,73.843
 4275.000,241.436,184.575,7.075,-45.305,4.142,5.418,9.467,2.601,.050,.064,.201,100.936,-18.983,-11.248,3.000,13.189,6.792,.194,74.881
 4275.500,248.850,196.396,6.869,-44.740,4.018,5.092,9.462,2.599,.051,.065,.219,105.209,-18.589,-10.720,3.000,11.767,6.113,.206,76.616
 4276.000,257.298,213.407,6.146,-44.151,3.886,4.686,9.459,2.599,.054,.065,.232,101.664,-17.563,-10.168,3.000,10.109,5.407,.222,78.906
 4276.500,266.504,231.382,5.494,-43.582,3.752,4.322,9.467,2.601,.058,.064,.245,96.710,-16.393,-9.636,2.987,9.313,4.992,.237,81.103
 4277.000,271.740,243.477,4.945,-43.066,3.680,4.107,9.464,2.607,.063,.060,.256,105.026,-15.743,-9.157,3.000,8.457,4.594,.246,82.247
 4277.500,269.309,242.560,4.747,-42.631,3.713,4.123,9.465,2.615,.068,.055,.259,106.646,-17.232,-8.759,3.000,8.553,4.645,.240,81.496
 4278.000,257.476,227.756,4.983,-42.298,3.884,4.391,9.466,2.623,.072,.051,.253,98.098,-22.345,-8.464,3.007,9.780,5.171,.218,78.392
 4278.500,233.805,205.869,5.885,-42.077,4.277,4.857,9.442,2.627,.073,.048,.235,88.902,-29.619,-8.280,2.996,18.328,7.999,.183,73.463
 4279.000,211.253,182.496,9.831,-41.956,4.734,5.480,9.408,2.630,.070,.047,.193,77.557,-37.386,-8.196,2.915,50.789,18.344,.146,68.218
 4279.500,194.644,158.305,19.324,-41.910,5.138,6.317,9.406,2.632,.063,.045,.141,56.002,-43.254,-8.188,2.823,81.260,29.751,.118,64.128
 4280.000,176.683,134.094,24.579,-41.923,5.660,7.457,9.406,2.634,.054,.044,.110,47.653,-44.286,-8.237,2.786,64.446,25.024,.102,61.937
 4280.500,156.076,112.658,19.062,-42.005,6.407,8.876,9.407,2.634,.047,.044,.093,48.925,-40.094,-8.356,2.769,41.284,17.103,.099,61.570
 4281.000,133.762,96.630,15.803,-42.206,7.476,10.349,9.405,2.634,.043,.045,.088,51.631,-31.740,-8.595,2.764,38.296,15.392,.105,62.317
 4281.500,116.775,87.753,15.217,-42.600,8.564,11.396,9.401,2.635,.042,.044,.091,50.027,-22.578,-9.026,2.768,34.217,13.795,.113,63.510
 4282.000,111.605,86.843,13.848,-43.262,8.960,11.515,9.407,2.639,.043,.042,.098,51.332,-16.339,-9.725,2.779,27.656,11.616,.123,64.899
 4282.500,115.703,92.685,11.962,-44.243,8.643,10.789,9.412,2.643,.049,.039,.107,59.253,-12.871,-10.743,2.797,20.801,9.082,.134,66.414
 4283.000,125.022,103.478,10.074,-45.548,7.999,9.664,9.405,2.641,.060,.040,.123,70.162,-10.551,-12.085,2.822,18.343,8.244,.146,68.150
 4283.500,143.321,119.686,9.052,-47.118,6.977,8.355,9.403,2.632,.073,.046,.148,74.868,-10.064,-13.693,2.851,19.156,8.397,.160,70.161
 4284.000,166.806,142.771,7.614,-48.831,5.995,7.004,9.401,2.617,.085,.054,.176,74.687,-9.853,-15.443,2.878,16.924,7.635,.175,72.216
 4284.500,189.506,171.010,5.791,-50.516,5.277,5.848,9.395,2.597,.089,.066,.195,75.843,-8.888,-17.165,2.890,13.494,6.335,.187,74.025
 4285.000,210.077,199.172,5.117,-51.999,4.760,5.021,9.399,2.570,.082,.082,.207,83.491,-8.000,-18.685,2.898,11.530,5.443,.196,75.263
 4285.500,229.227,222.369,5.054,-53.146,4.363,4.497,9.399,2.540,.068,.099,.216,87.506,-8.182,-19.868,2.903,10.283,5.184,.200,75.739
 4286.000,249.083,238.945,5.060,-53.877,4.015,4.185,9.396,2.517,.056,.113,.223,85.307,-9.797,-20.637,2.898,10.073,5.108,.200,75.800
 4286.500,268.722,250.950,5.047,-54.169,3.721,3.985,9.397,2.508,.051,.118,.225,84.141,-12.101,-20.966,2.894,10.596,5.143,.201,75.944
 4287.000,284.426,261.013,5.050,-54.027,3.516,3.831,9.397,2.510,.052,.117,.222,82.150,-14.026,-20.861,2.888,11.388,5.326,.204,76.338
 4287.500,297.019,269.377,5.034,-53.485,3.367,3.712,9.391,2.516,.054,.113,.221,82.689,-15.461,-20.356,2.890,11.330,5.409,.208,76.907
 4288.000,306.612,275.465,4.995,-52.605,3.261,3.630,9.387,2.521,.056,.111,.227,88.250,-16.376,-19.513,2.912,11.453,5.385,.212,77.487
 4288.500,314.811,279.606,4.891,-51.479,3.177,3.576,9.397,2.525,.056,.108,.235,93.008,-17.052,-18.425,2.944,10.250,5.087,.215,77.901
 4289.000,321.684,282.191,4.806,-50.214,3.109,3.544,9.400,2.533,.056,.104,.245,91.662,-17.626,-17.197,2.938,9.150,4.928,.216,78.004
 4289.500,327.345,283.426,4.810,-48.904,3.055,3.528,9.396,2.545,.056,.096,.257,89.560,-18.207,-15.924,2.953,9.225,4.960,.214,77.760
 4290.000,332.444,283.870,4.873,-47.612,3.008,3.523,9.391,2.559,.058,.088,.265,92.345,-18.853,-14.669,2.976,9.395,5.018,.211,77.327
 4290.500,337.259,284.354,4.941,-46.371,2.965,3.517,9.391,2.569,.060,.082,.267,101.650,-19.486,-13.466,3.000,9.151,4.958,.209,77.052
 4291.000,341.677,285.478,4.917,-45.210,2.927,3.503,9.392,2.573,.061,.080,.268,101.400,-20.004,-12.342,3.000,8.454,4.773,.210,77.180
 4291.500,345.770,287.373,4.833,-44.169,2.892,3.480,9.392,2.570,.062,.082,.271,98.158,-20.413,-11.337,3.002,8.098,4.711,.212,77.494
 4292.000,350.067,289.959,4.851,-43.300,2.857,3.449,9.390,2.561,.063,.087,.272,100.857,-20.794,-10.506,3.000,7.891,4.575,.213,77.649
 4292.500,354.446,293.305,4.909,-42.651,2.821,3.409,9.387,2.547,.063,.095,.271,102.006,-21.098,-9.894,3.000,7.330,4.280,.214,77.815
 4293.000,358.444,297.467,4.866,-42.246,2.790,3.362,9.388,2.532,.063,.104,.268,100.757,-21.236,-9.526,3.000,7.070,4.136,.218,78.308
 4293.500,359.865,301.798,4.758,-42.079,2.779,3.313,9.389,2.520,.062,.111,.265,104.183,-21.194,-9.397,3.000,6.914,4.111,.222,78.972
 4294.000,355.467,304.123,4.620,-42.127,2.813,3.288,9.390,2.517,.060,.113,.264,111.616,-21.671,-9.481,3.000,6.714,4.042,.224,79.176
 4294.500,342.647,300.294,4.500,-42.368,2.918,3.330,9.390,2.530,.058,.105,.258,107.996,-24.967,-9.759,3.000,6.884,4.083,.214,77.819
 4295.000,318.750,284.742,4.509,-42.795,3.137,3.512,9.355,2.561,.060,.087,.239,97.964,-33.985,-10.224,2.983,9.215,4.669,.187,73.996
 4295.500,286.040,254.176,5.408,-43.405,3.496,3.934,9.329,2.602,.065,.063,.205,91.643,-48.527,-10.871,2.934,25.138,7.751,.146,68.220
 4296.000,253.028,212.292,10.085,-44.176,3.952,4.710,9.339,2.639,.067,.041,.150,73.243,-64.675,-11.679,2.860,49.505,13.061,.103,62.048
 4296.500,219.801,168.198,22.741,-45.049,4.550,5.945,9.346,2.663,.066,.028,.102,54.243,-77.441,-12.589,2.801,61.769,17.153,.067,56.986
 4297.000,188.892,129.949,51.943,-45.934,5.294,7.695,9.348,2.675,.062,.020,.072,49.781,-84.394,-13.511,2.775,84.594,23.185,.047,54.087
 4297.500,158.653,100.395,85.218,-46.730,6.303,9.961,9.356,2.685,.061,.014,.063,41.110,-83.970,-14.345,2.768,94.097,26.379,.042,53.460
 4298.000,129.071,78.845,74.410,-47.361,7.748,12.683,9.437,2.696,.064,.008,.062,35.842,-75.812,-15.012,2.773,77.121,22.226,.048,54.250
 4298.500,101.285,63.816,41.395,-47.785,9.873,15.670,9.473,2.698,.068,.007,.062,37.191,-60.798,-15.474,2.775,52.687,16.462,.056,55.376
 4299.000,81.438,53.785,25.913,-47.999,12.279,18.593,9.466,2.688,.067,.013,.061,37.834,-43.602,-15.724,2.767,44.949,14.555,.062,56.213
 4299.500,71.259,47.706,24.511,-48.013,14.033,20.962,9.474,2.670,.061,.023,.061,37.544,-29.817,-15.776,2.754,50.423,15.035,.064,56.609
 4300.000,68.452,45.323,23.667,-47.841,14.609,22.064,9.505,2.648,.051,.036,.063,40.108,-22.028,-15.641,2.742,44.771,13.728,.066,56.804
 4300.500,73.491,47.057,23.363,-47.486,13.607,21.251,9.563,2.622,.041,.052,.068,41.697,-20.329,-15.323,2.731,45.513,13.834,.071,57.553
 4301.000,86.364,54.549,25.546,-46.942,11.579,18.332,9.671,2.588,.032,.071,.077,41.644,-21.518,-14.816,2.719,54.304,14.939,.086,59.623
 4301.500,105.224,70.851,17.720,-46.212,9.503,14.114,9.758,2.555,.029,.091,.089,49.369,-21.499,-14.123,2.718,40.821,11.814,.112,63.333
 4302.000,127.823,97.983,9.585,-45.331,7.823,10.206,9.904,2.535,.035,.102,.107,72.927,-18.199,-13.280,2.755,20.342,7.952,.149,68.549
 4302.500,156.127,134.056,6.196,-44.374,6.405,7.460,10.155,2.534,.050,.103,.136,94.030,-13.106,-12.360,2.952,11.471,5.857,.189,74.232
 4303.000,184.635,173.942,4.753,-43.444,5.416,5.749,10.416,2.544,.067,.097,.191,104.758,-7.375,-11.466,3.000,7.418,4.601,.222,78.916
 4303.500,211.964,212.507,4.306,-42.639,4.718,4.706,10.873,2.550,.080,.093,.251,105.881,-3.836,-10.699,3.000,5.708,4.021,.244,82.028
 4304.000,241.253,245.769,4.258,-42.030,4.145,4.069,11.083,2.547,.087,.095,.295,105.133,-4.069,-10.128,3.000,5.105,3.820,.257,83.861
 4304.500,274.350,271.829,4.307,-41.646,3.645,3.679,10.864,2.535,.091,.103,.334,102.922,-7.089,-9.781,3.000,4.896,3.575,.264,84.894
 4305.000,306.048,291.878,4.325,-41.480,3.267,3.426,10.891,2.518,.095,.112,.358,98.007,-10.545,-9.652,2.994,5.316,3.565,.268,85.471
 4305.500,335.393,308.377,4.283,-41.500,2.982,3.243,11.247,2.497,.101,.124,.354,98.082,-13.495,-9.709,2.994,5.197,3.639,.270,85.725
 4306.000,359.926,322.036,4.180,-41.660,2.778,3.105,11.503,2.472,.110,.139,.332,97.613,-15.421,-9.906,2.993,4.303,3.555,.273,86.154
 4306.500,378.453,331.103,4.024,-41.911,2.642,3.020,11.728,2.444,.125,.155,.317,96.788,-16.317,-10.194,2.986,4.038,3.332,.284,87.733
 4307.000,392.824,335.544,3.848,-42.213,2.546,2.980,12.035,2.417,.143,.171,.324,99.895,-16.620,-10.533,3.000,4.328,3.225,.307,90.906
 4307.500,406.063,339.357,3.739,-42.536,2.463,2.947,12.163,2.385,.159,.190,.355,102.096,-16.861,-10.893,3.000,3.984,3.092,.332,94.420
 4308.000,418.612,345.260,3.665,-42.856,2.389,2.896,12.192,2.344,.165,.214,.393,97.836,-17.221,-11.250,2.991,3.882,2.984,.342,95.954
 4308.500,432.065,352.063,3.623,-43.144,2.315,2.840,12.135,2.297,.165,.241,.413,100.048,-17.887,-11.575,3.000,3.865,2.917,.337,95.237
 4309.000,447.158,358.227,3.612,-43.371,2.236,2.792,12.113,2.262,.165,.262,.407,104.345,-18.882,-11.840,3.000,3.597,2.809,.329,94.095
 4309.500,460.303,363.469,3.593,-43.518,2.172,2.751,12.080,2.251,.169,.268,.393,100.185,-19.850,-12.024,3.000,3.287,2.682,.325,93.443
 4310.000,467.945,367.675,3.574,-43.586,2.137,2.720,11.905,2.263,.175,.262,.393,94.618,-20.491,-12.129,2.977,3.287,2.654,.320,92.721
 4310.500,472.514,370.334,3.601,-43.602,2.116,2.700,11.815,2.288,.180,.247,.399,98.658,-21.013,-12.182,2.994,3.590,2.684,.311,91.534
 4311.000,472.959,370.931,3.647,-43.609,2.114,2.696,11.686,2.315,.179,.231,.390,97.159,-21.301,-12.227,2.988,3.738,2.756,.304,90.527
 4311.500,467.585,369.198,3.692,-43.666,2.139,2.709,11.243,2.336,.171,.219,.362,92.587,-21.233,-12.320,2.968,3.846,2.857,.303,90.408
 4312.000,453.640,364.743,3.693,-43.833,2.204,2.742,11.110,2.356,.159,.207,.328,90.995,-20.795,-12.524,2.961,4.172,2.959,.306,90.754
 4312.500,431.223,355.161,3.673,-44.167,2.319,2.816,11.128,2.388,.144,.188,.305,88.161,-20.525,-12.896,2.948,4.363,3.047,.297,89.468
 4313.000,400.702,334.972,3.729,-44.729,2.496,2.985,10.943,2.436,.126,.160,.296,82.099,-21.033,-13.494,2.932,5.198,3.476,.266,85.189
 4313.500,368.582,301.824,4.174,-45.569,2.713,3.313,10.659,2.490,.106,.129,.290,83.486,-22.847,-14.372,2.957,8.997,4.897,.224,79.128
 4314.000,339.648,263.927,5.529,-46.732,2.944,3.789,10.635,2.536,.087,.102,.275,84.928,-25.381,-15.572,2.965,12.418,6.233,.182,73.254
 4314.500,314.156,233.088,7.157,-48.228,3.183,4.290,10.642,2.565,.073,.085,.250,83.318,-27.218,-17.105,2.949,14.571,6.710,.156,69.503
 4315.000,290.284,212.286,7.785,-50.014,3.445,4.711,10.644,2.578,.065,.077,.226,81.453,-27.198,-18.928,2.928,16.208,6.692,.149,68.619
 4315.500,268.902,198.017,7.549,-51.976,3.719,5.050,10.642,2.580,.061,.076,.207,79.045,-25.362,-20.927,2.900,15.790,6.401,.154,69.300
 4316.000,248.258,188.393,7.023,-53.949,4.028,5.308,10.632,2.575,.060,.079,.192,81.334,-22.056,-22.938,2.881,16.896,6.553,.160,70.177
 4316.500,234.222,183.622,6.746,-55.750,4.269,5.446,10.636,2.566,.058,.084,.183,77.235,-19.033,-24.776,2.858,20.108,7.262,.165,70.906
 4317.000,229.591,183.568,6.832,-57.218,4.356,5.448,10.636,2.559,.058,.089,.178,71.506,-17.474,-26.281,2.835,22.504,7.818,.170,71.516
 4317.500,230.415,187.003,6.747,-58.239,4.340,5.347,10.636,2.552,.059,.092,.172,75.342,-16.985,-27.339,2.834,20.879,7.422,.173,71.943
 4318.000,234.919,191.991,6.489,-58.745,4.257,5.209,10.636,2.546,.061,.096,.167,75.042,-17.302,-27.883,2.824,19.696,7.238,.174,72.156
 4318.500,239.539,196.602,6.461,-58.705,4.175,5.086,10.642,2.540,.063,.100,.173,70.781,-17.846,-27.879,2.817,21.095,7.568,.174,72.160
 4319.000,240.075,199.769,6.598,-58.115,4.165,5.006,10.641,2.537,.066,.101,.191,74.509,-17.900,-27.326,2.845,21.983,7.743,.173,72.004
 4319.500,238.812,201.342,6.672,-57.005,4.187,4.967,10.642,2.540,.067,.099,.211,76.158,-17.692,-26.253,2.873,21.461,7.617,.172,71.898
 4320.000,237.130,201.493,6.653,-55.451,4.217,4.963,10.642,2.545,.065,.097,.224,78.609,-17.278,-24.737,2.897,20.234,7.331,.173,72.046
 4320.500,235.249,200.492,6.550,-53.583,4.251,4.988,10.647,2.545,.056,.097,.227,82.288,-16.637,-22.906,2.908,18.097,6.968,.177,72.477
 4321.000,233.430,198.547,6.397,-51.578,4.284,5.037,10.645,2.540,.046,.099,.222,82.020,-15.886,-20.938,2.900,15.677,6.657,.181,73.139
 4321.500,231.661,195.873,6.324,-49.630,4.317,5.105,10.642,2.538,.039,.101,.219,87.317,-15.176,-19.027,2.904,14.186,6.427,.186,73.869
 4322.000,229.248,192.811,6.252,-47.905,4.362,5.186,10.642,2.544,.039,.097,.223,91.534,-14.566,-17.339,2.932,13.106,6.105,.190,74.326
 4322.500,225.915,189.396,6.180,-46.498,4.426,5.280,10.645,2.555,.043,.091,.228,95.983,-14.149,-15.970,2.967,13.240,6.110,.189,74.228
 4323.000,222.513,185.541,6.314,-45.410,4.494,5.390,10.644,2.564,.047,.085,.229,92.695,-14.092,-14.919,2.941,14.053,6.348,.185,73.664
 4323.500,220.334,181.936,6.595,-44.565,4.539,5.496,10.644,2.569,.050,.083,.228,84.898,-14.416,-14.111,2.926,14.376,6.470,.181,73.067
 4324.000,220.559,179.840,6.848,-43.852,4.534,5.561,10.649,2.572,.053,.080,.233,83.763,-14.892,-13.435,2.935,14.278,6.509,.180,72.971
 4324.500,225.010,180.667,7.019,-43.177,4.444,5.535,10.645,2.580,.057,.076,.242,87.785,-15.303,-12.797,2.957,13.977,6.412,.185,73.701
 4325.000,234.891,186.270,6.837,-42.496,4.257,5.369,10.644,2.591,.062,.070,.250,90.264,-15.438,-12.153,2.978,12.554,5.806,.195,75.163
 4325.500,246.080,197.818,5.998,-41.824,4.064,5.055,10.646,2.598,.066,.065,.255,93.705,-14.572,-11.518,3.003,9.960,5.021,.209,77.034
 4326.000,255.976,214.188,5.111,-41.212,3.907,4.669,10.645,2.594,.067,.068,.265,96.204,-12.830,-10.943,3.014,8.776,4.619,.222,78.937
 4326.500,268.222,232.452,4.676,-40.716,3.728,4.302,10.634,2.579,.065,.077,.280,102.144,-11.599,-10.485,3.000,8.224,4.393,.233,80.438
 4327.000,282.561,249.728,4.527,-40.368,3.539,4.004,10.627,2.565,.064,.085,.289,107.120,-11.424,-10.174,3.000,7.969,4.278,.239,81.313
 4327.500,299.200,264.652,4.502,-40.160,3.342,3.779,10.619,2.559,.065,.088,.293,100.381,-12.399,-10.003,3.000,8.039,4.289,.242,81.727
 4328.000,317.160,277.059,4.498,-40.056,3.153,3.609,10.616,2.562,.068,.087,.297,93.807,-14.076,-9.936,3.070,8.090,4.331,.243,81.949
 4328.500,334.160,286.855,4.491,-40.008,2.993,3.486,10.612,2.564,.069,.086,.297,92.465,-15.827,-9.925,3.054,8.018,4.287,.245,82.150
 4329.000,347.238,293.787,4.474,-39.979,2.880,3.404,10.590,2.561,.067,.087,.290,91.950,-17.135,-9.934,3.019,7.796,4.287,.247,82.429
 4329.500,355.737,298.259,4.437,-39.952,2.811,3.353,10.510,2.556,.064,.090,.283,93.642,-17.909,-9.943,3.000,7.684,4.350,.249,82.701
 4330.000,359.717,301.317,4.411,-39.931,2.780,3.319,10.500,2.551,.060,.093,.284,102.239,-18.198,-9.959,3.000,7.868,4.314,.249,82.783
 4330.500,364.952,303.891,4.410,-39.942,2.740,3.291,10.499,2.545,.057,.097,.291,107.303,-18.646,-10.008,3.000,7.886,4.283,.249,82.776
 4331.000,370.705,306.863,4.409,-40.030,2.698,3.259,10.529,2.536,.054,.102,.297,109.441,-19.140,-10.132,3.000,7.655,4.269,.249,82.770
 4331.500,376.641,311.377,4.404,-40.245,2.655,3.211,10.595,2.521,.053,.111,.302,109.143,-19.554,-10.385,3.000,7.414,4.214,.247,82.510
 4332.000,384.085,318.481,4.399,-40.640,2.604,3.140,10.631,2.486,.055,.131,.309,105.321,-19.905,-10.818,3.000,7.079,4.146,.248,82.523
 4332.500,391.570,327.859,4.368,-41.246,2.554,3.050,10.766,2.414,.061,.173,.319,103.487,-20.128,-11.460,3.000,6.282,3.981,.264,84.846
 4333.000,395.195,337.064,4.210,-42.057,2.530,2.967,10.971,2.313,.072,.232,.327,99.031,-20.997,-12.308,2.996,5.145,3.543,.300,89.912
 4333.500,389.078,342.630,3.840,-43.031,2.570,2.919,10.981,2.227,.092,.282,.319,91.004,-25.762,-13.320,2.961,4.055,3.019,.326,93.647
 4334.000,368.330,337.514,3.518,-44.099,2.715,2.963,10.614,2.194,.113,.302,.297,85.863,-39.083,-14.425,2.937,5.008,3.016,.314,91.881
 4334.500,335.194,310.444,4.097,-45.187,2.983,3.221,9.916,2.217,.123,.288,.279,79.915,-59.817,-15.550,2.888,11.631,5.118,.260,84.323
 4335.000,297.949,260.074,8.706,-46.232,3.356,3.845,9.620,2.282,.115,.250,.266,70.960,-81.414,-16.632,2.792,33.751,13.094,.186,73.822
 4335.500,259.448,200.907,26.701,-47.187,3.854,4.977,9.555,2.353,.094,.209,.255,54.132,-98.701,-17.624,2.775,68.891,22.414,.130,65.960
 4336.000,224.691,148.812,70.641,-48.010,4.451,6.720,9.527,2.396,.071,.184,.250,36.365,-110.077,-18.485,2.780,82.677,23.484,.114,63.680
 4336.500,190.027,109.504,128.857,-48.666,5.262,9.132,9.461,2.412,.059,.174,.253,30.680,-114.114,-19.177,2.792,80.923,21.936,.112,63.400
 4337.000,153.841,81.018,154.031,-49.119,6.500,12.343,9.452,2.426,.060,.166,.253,33.684,-109.884,-19.668,2.800,79.920,22.633,.103,62.065
 4337.500,120.574,61.981,133.521,-49.347,8.294,16.134,9.497,2.433,.069,.162,.237,39.654,-97.914,-19.933,2.790,76.085,22.767,.098,61.298
 4338.000,99.890,54.000,83.707,-49.345,10.011,18.518,9.706,2.418,.080,.171,.209,42.962,-81.930,-19.968,2.754,46.126,16.572,.108,62.746
 4338.500,91.391,57.600,37.669,-49.136,10.942,17.361,10.026,2.388,.095,.188,.185,49.548,-64.403,-19.796,2.721,16.521,9.011,.127,65.513
 4339.000,88.680,67.943,16.852,-48.770,11.277,14.718,9.823,2.369,.109,.199,.179,60.500,-45.962,-19.467,2.722,7.148,5.228,.144,67.815
 4339.500,89.122,76.343,11.411,-48.312,11.221,13.099,9.434,2.374,.115,.197,.175,63.350,-31.567,-19.046,2.726,8.318,5.366,.145,67.977
 4340.000,89.476,76.720,11.221,-47.827,11.176,13.034,9.141,2.403,.112,.179,.155,59.174,-28.538,-18.599,2.714,11.946,6.577,.126,65.271
 4340.500,87.748,69.538,17.145,-47.356,11.396,14.381,8.817,2.454,.100,.150,.124,50.505,-36.099,-18.165,2.700,27.047,9.635,.096,61.086
 4341.000,86.166,59.511,37.678,-46.908,11.606,16.803,8.755,2.516,.082,.113,.093,44.511,-46.545,-17.754,2.698,46.304,13.653,.068,57.143
 4341.500,83.781,50.944,62.745,-46.466,11.936,19.629,8.708,2.576,.065,.079,.067,40.166,-53.825,-17.349,2.703,56.262,16.194,.049,54.391
 4342.000,77.635,45.254,66.446,-46.009,12.881,22.097,8.682,2.619,.051,.053,.053,39.654,-55.149,-16.929,2.713,58.976,16.882,.041,53.257
 4342.500,68.025,41.231,52.856,-45.528,14.700,24.254,8.656,2.644,.042,.038,.046,43.502,-51.100,-16.485,2.721,54.193,15.903,.040,53.119
 4343.000,56.727,37.204,47.779,-45.034,17.628,26.879,8.636,2.655,.038,.032,.042,40.883,-43.666,-16.028,2.722,51.586,15.137,.040,53.183
 4343.500,46.876,32.860,54.237,-44.541,21.333,30.432,8.636,2.657,.037,.031,.040,37.906,-35.857,-15.573,2.721,51.746,14.802,.040,53.176
 4344.000,41.422,28.997,54.428,-44.064,24.142,34.486,8.635,2.656,.039,.032,.039,36.859,-31.085,-15.133,2.719,47.542,14.554,.040,53.098
 4344.500,39.454,26.326,51.754,-43.609,25.346,37.986,8.636,2.652,.042,.034,.039,35.633,-29.373,-14.715,2.716,47.160,15.145,.039,53.024
 4345.000,39.418,24.909,55.983,-43.174,25.369,40.147,8.636,2.647,.044,.037,.039,34.690,-29.127,-14.317,2.713,50.372,15.743,.039,53.049
 4345.500,40.413,24.691,58.032,-42.758,24.744,40.500,8.636,2.645,.045,.038,.039,37.351,-28.906,-13.938,2.713,47.213,15.481,.041,53.313
 4346.000,41.757,25.823,50.345,-42.358,23.948,38.726,8.636,2.646,.044,.038,.041,40.915,-27.567,-13.576,2.716,42.769,15.299,.046,53.975
 4346.500,42.982,28.256,44.203,-41.975,23.266,35.391,8.637,2.646,.042,.037,.044,43.438,-24.594,-13.230,2.721,44.259,16.292,.053,55.044
 4347.000,44.292,31.555,39.104,-41.610,22.577,31.691,8.636,2.641,.040,.040,.048,42.578,-20.583,-12.901,2.721,42.291,16.179,.062,56.256
 4347.500,45.375,35.144,29.022,-41.264,22.038,28.454,8.636,2.628,.036,.048,.051,50.123,-16.168,-12.592,2.720,37.353,15.620,.069,57.286
 4348.000,46.451,38.480,24.575,-40.937,21.528,25.988,8.636,2.613,.033,.057,.053,54.415,-12.658,-12.303,2.716,40.834,17.202,.074,57.987
 4348.500,48.197,41.534,27.139,-40.629,20.748,24.077,8.636,2.603,.031,.062,.055,50.979,-11.003,-12.032,2.711,46.003,18.899,.078,58.526
 4349.000,51.585,45.245,29.348,-40.332,19.385,22.102,8.636,2.606,.031,.061,.057,48.254,-11.150,-11.772,2.713,45.848,18.609,.084,59.355
 4349.500,56.007,50.626,25.895,-40.040,17.855,19.753,8.636,2.620,.033,.053,.059,51.235,-11.992,-11.517,2.725,38.398,15.628,.093,60.661
 4350.000,59.675,57.173,18.594,-39.746,16.757,17.491,8.636,2.636,.038,.043,.062,54.421,-14.060,-11.260,2.738,27.649,11.494,.101,61.740
 4350.500,59.847,62.276,14.024,-39.449,16.709,16.058,8.636,2.649,.043,.036,.062,56.701,-18.931,-11.001,2.746,23.064,9.814,.099,61.518
 4351.000,57.739,62.690,20.395,-39.152,17.319,15.951,8.635,2.654,.046,.033,.060,51.706,-26.944,-10.741,2.745,35.539,13.647,.087,59.767
 4351.500,56.616,57.767,49.394,-38.855,17.663,17.311,8.635,2.655,.046,.032,.057,41.786,-35.470,-10.481,2.740,71.011,25.308,.069,57.294
 4352.000,57.082,50.660,77.689,-38.558,17.518,19.739,8.636,2.653,.045,.034,.051,36.890,-40.970,-10.221,2.732,89.264,32.230,.055,55.336
 4352.500,58.087,45.321,65.287,-38.272,17.216,22.065,8.667,2.650,.046,.035,.047,36.472,-41.311,-9.972,2.724,74.316,26.835,.052,54.805
 4353.000,59.493,43.527,37.833,-38.024,16.809,22.974,8.702,2.644,.048,.038,.045,33.382,-36.892,-9.761,2.718,53.715,18.889,.058,55.725
 4353.500,62.525,45.732,28.487,-37.858,15.994,21.866,8.696,2.628,.050,.048,.047,34.561,-30.209,-9.632,2.710,53.682,16.576,.070,57.437
 4354.000,68.839,53.458,23.672,-37.821,14.527,18.706,8.718,2.595,.054,.067,.052,35.897,-24.207,-9.632,2.698,44.244,12.694,.086,59.684
 4354.500,81.956,69.179,19.949,-37.940,12.202,14.455,8.786,2.547,.066,.095,.063,40.025,-21.360,-9.789,2.684,40.121,11.290,.113,63.490
 4355.000,104.275,93.559,17.687,-38.213,9.590,10.688,8.910,2.500,.089,.123,.085,52.919,-20.997,-10.099,2.688,31.597,9.787,.155,69.426
 4355.500,130.428,123.441,10.786,-38.607,7.667,8.101,9.088,2.475,.116,.138,.114,72.399,-19.450,-10.529,2.741,12.674,5.844,.200,75.808
 4356.000,150.503,152.965,6.153,-39.074,6.644,6.537,9.071,2.479,.135,.135,.148,89.382,-15.634,-11.034,2.916,5.735,4.174,.232,80.299
 4356.500,163.786,174.064,5.614,-39.571,6.106,5.745,9.041,2.504,.134,.120,.183,97.060,-14.154,-11.568,2.976,6.641,4.397,.239,81.275
 4357.000,170.418,180.535,6.845,-40.069,5.868,5.539,8.919,2.537,.115,.101,.197,100.699,-17.937,-12.104,3.000,10.146,5.349,.218,78.348
 4357.500,176.435,174.476,9.694,-40.553,5.668,5.732,8.907,2.564,.088,.085,.174,100.658,-25.728,-12.624,3.000,16.514,7.246,.183,73.432
 4358.000,185.881,163.753,15.020,-41.004,5.380,6.107,8.902,2.575,.068,.079,.147,84.285,-33.678,-13.113,2.878,26.323,11.633,.154,69.346
 4358.500,193.962,155.884,18.892,-41.396,5.156,6.415,8.896,2.563,.060,.086,.135,74.270,-37.907,-13.542,2.797,30.731,14.579,.144,67.850
 4359.000,193.893,154.984,15.540,-41.700,5.157,6.452,8.934,2.534,.065,.103,.137,79.332,-36.798,-13.883,2.829,23.430,11.378,.154,69.345
 4359.500,183.089,159.100,9.695,-41.904,5.462,6.285,8.998,2.508,.080,.118,.145,89.552,-32.406,-14.124,2.917,13.849,7.350,.173,71.971
 4360.000,164.031,159.759,6.744,-42.027,6.096,6.259,8.976,2.500,.097,.123,.151,95.200,-30.287,-14.284,2.961,9.363,5.581,.178,72.694
 4360.500,143.065,148.615,8.292,-42.103,6.990,6.729,8.827,2.513,.101,.115,.153,88.427,-34.236,-14.397,2.908,18.992,8.580,.160,70.203
 4361.000,128.816,126.421,17.783,-42.163,7.763,7.910,8.812,2.540,.090,.099,.144,74.420,-42.255,-14.495,2.796,52.381,19.715,.126,65.265
 4361.500,122.741,102.646,38.254,-42.209,8.147,9.742,8.805,2.573,.071,.080,.122,57.889,-49.829,-14.577,2.766,72.465,28.991,.091,60.364
 4362.000,118.941,85.743,48.183,-42.214,8.408,11.663,8.814,2.609,.056,.059,.099,47.620,-52.846,-14.619,2.759,59.760,27.329,.075,58.055
 4362.500,111.562,76.624,37.350,-42.145,8.964,13.051,8.814,2.640,.049,.041,.085,46.823,-49.097,-14.588,2.764,46.013,21.803,.077,58.356
 4363.000,97.849,71.836,24.581,-41.990,10.220,13.921,8.815,2.659,.049,.030,.079,47.709,-38.431,-14.470,2.770,36.268,17.377,.086,59.654
 4363.500,83.510,68.732,17.601,-41.770,11.975,14.549,8.811,2.666,.050,.026,.079,50.435,-24.887,-14.287,2.776,28.904,13.997,.094,60.776
 4364.000,73.515,66.244,15.283,-41.528,13.603,15.096,8.803,2.670,.050,.023,.082,54.755,-14.011,-14.083,2.784,26.171,12.484,.097,61.178
 4364.500,69.999,63.966,15.266,-41.304,14.286,15.633,8.796,2.678,.050,.019,.085,55.645,-9.849,-13.896,2.794,27.719,12.265,.094,60.746
 4365.000,72.589,62.158,17.850,-41.109,13.776,16.088,8.796,2.688,.049,.013,.084,50.576,-11.985,-13.737,2.798,35.736,14.656,.088,59.936
 4365.500,77.550,61.581,22.965,-40.923,12.895,16.239,8.803,2.694,.046,.010,.080,44.160,-15.795,-13.589,2.793,46.289,17.349,.083,59.286
 4366.000,80.748,62.441,22.664,-40.718,12.384,16.015,8.802,2.688,.043,.013,.075,38.538,-17.314,-13.421,2.782,40.040,15.480,.081,59.029
 4366.500,83.243,64.127,16.980,-40.488,12.013,15.594,8.793,2.675,.042,.020,.073,38.540,-16.977,-13.228,2.771,32.999,12.856,.083,59.212
 4367.000,88.225,66.944,15.986,-40.264,11.335,14.938,8.790,2.653,.041,.033,.075,46.436,-17.144,-13.042,2.761,34.529,12.271,.085,59.496
 4367.500,97.297,73.710,16.342,-40.107,10.278,13.567,8.797,2.604,.037,.062,.080,49.075,-18.871,-12.922,2.735,35.805,12.921,.088,59.906
 4368.000,114.434,88.700,17.801,-40.074,8.739,11.274,8.799,2.507,.026,.119,.089,47.332,-22.440,-12.926,2.691,46.450,15.994,.104,62.184
 4368.500,137.243,114.533,17.076,-40.187,7.286,8.731,8.913,2.377,.014,.195,.105,52.389,-24.738,-13.076,2.649,36.015,13.134,.146,68.096
 4369.000,156.127,148.278,10.877,-40.424,6.405,6.744,9.125,2.270,.011,.257,.124,63.837,-22.248,-13.349,2.673,14.005,6.563,.202,76.015
 4369.500,171.981,179.609,6.065,-40.738,5.815,5.568,9.002,2.224,.019,.284,.148,75.648,-16.757,-13.701,2.786,5.692,3.665,.247,82.382
 4370.000,189.147,199.001,5.026,-41.100,5.287,5.025,8.907,2.242,.034,.274,.189,83.694,-12.224,-14.100,2.873,6.782,3.689,.269,85.555
 4370.500,210.167,208.514,5.940,-41.520,4.758,4.796,8.973,2.301,.056,.239,.238,83.651,-12.025,-14.523,2.894,10.191,4.906,.269,85.558
 4371.000,226.401,215.380,6.200,-42.037,4.417,4.643,9.239,2.371,.083,.198,.254,89.967,-15.455,-15.043,2.935,10.228,5.266,.255,83.616
 4371.500,234.449,217.962,5.511,-42.690,4.265,4.588,9.035,2.436,.103,.160,.241,97.144,-21.264,-15.699,2.977,8.376,5.049,.241,81.579
 4372.000,234.211,209.125,7.222,-43.483,4.270,4.782,8.765,2.492,.107,.128,.217,90.825,-27.717,-16.495,2.927,15.630,7.470,.223,79.058
 4372.500,225.144,190.016,11.529,-44.387,4.442,5.263,8.753,2.532,.094,.104,.200,77.886,-32.217,-17.402,2.861,24.829,11.347,.196,75.172
 4373.000,215.692,170.834,13.957,-45.352,4.636,5.854,8.779,2.540,.076,.100,.186,74.231,-33.989,-18.370,2.840,24.362,12.266,.176,72.354
 4373.500,211.804,160.219,13.389,-46.333,4.721,6.241,8.805,2.506,.067,.119,.174,72.022,-33.127,-19.354,2.805,21.505,11.290,.179,72.765
 4374.000,209.737,159.558,10.567,-47.311,4.768,6.267,8.808,2.445,.073,.155,.177,76.897,-29.226,-20.335,2.810,18.287,9.349,.196,75.175
 4374.500,205.305,166.078,7.390,-48.302,4.871,6.021,8.895,2.367,.085,.201,.201,81.630,-22.796,-21.329,2.867,13.677,6.800,.218,78.358
 4375.000,202.578,176.821,6.474,-49.370,4.936,5.655,9.020,2.271,.094,.257,.236,83.887,-16.567,-22.400,2.894,9.470,5.110,.246,82.379
 4375.500,204.275,189.679,6.489,-50.630,4.895,5.272,9.326,2.174,.098,.314,.268,86.639,-13.194,-23.662,2.925,6.880,4.020,.275,86.442
 4376.000,204.601,200.869,5.834,-52.247,4.888,4.978,9.629,2.112,.104,.350,.289,92.651,-13.816,-25.282,2.968,4.892,3.489,.293,89.009
 4376.500,197.795,202.442,5.225,-54.414,5.056,4.940,9.586,2.112,.108,.350,.285,98.048,-19.443,-27.452,2.968,4.995,3.457,.284,87.681
 4377.000,187.314,186.522,6.518,-57.301,5.339,5.361,8.800,2.173,.101,.314,.266,90.062,-30.240,-30.342,2.942,10.183,5.465,.236,80.913
 4377.500,175.785,155.185,12.553,-60.988,5.689,6.444,8.364,2.283,.085,.250,.238,81.716,-43.005,-34.032,2.884,25.999,11.497,.170,71.601
 4378.000,161.579,122.066,21.842,-65.407,6.189,8.192,8.350,2.416,.068,.172,.177,65.879,-53.485,-38.454,2.750,43.743,19.743,.117,64.098
 4378.500,146.166,98.448,35.447,-70.324,6.841,10.158,8.336,2.531,.059,.105,.125,41.759,-59.755,-43.374,2.734,52.939,26.595,.087,59.836
 4379.000,128.021,84.078,49.385,-75.376,7.811,11.894,8.326,2.596,.058,.067,.102,32.103,-60.666,-48.429,2.748,48.478,26.775,.076,58.224
 4379.500,107.395,74.004,43.597,-80.155,9.311,13.513,8.320,2.622,.063,.051,.095,37.304,-56.609,-53.211,2.759,31.852,19.235,.076,58.224
 4380.000,89.576,65.742,31.751,-84.304,11.164,15.211,8.310,2.633,.070,.045,.098,36.557,-50.729,-57.363,2.769,16.455,12.569,.075,58.067
 4380.500,81.487,59.298,40.276,-87.595,12.272,16.864,8.311,2.636,.075,.043,.104,30.353,-47.931,-60.656,2.775,15.626,12.250,.068,57.083
 4381.000,81.953,55.306,50.281,-89.968,12.202,18.081,8.325,2.635,.076,.044,.106,28.507,-48.492,-63.033,2.775,13.737,11.358,.061,56.175
 4381.500,89.637,54.605,48.113,-91.536,11.156,18.313,8.317,2.633,.074,.045,.101,29.146,-50.606,-64.603,2.769,12.794,11.743,.059,55.797
 4382.000,105.538,58.102,38.459,-92.555,9.475,17.211,8.310,2.633,.072,.045,.095,32.060,-53.235,-65.626,2.764,24.239,18.165,.060,55.975
 4382.500,122.505,66.606,28.296,-93.392,8.163,15.014,8.327,2.629,.071,.047,.095,36.581,-53.254,-66.465,2.763,44.464,27.126,.068,57.056
 4383.000,142.258,81.328,25.921,-94.447,7.030,12.296,8.331,2.616,.071,.055,.106,40.398,-51.898,-67.524,2.767,60.932,34.694,.085,59.483
 4383.500,175.598,103.004,24.103,-96.069,5.695,9.708,8.326,2.592,.068,.069,.129,50.215,-51.881,-69.148,2.781,54.743,31.620,.110,63.081
 4384.000,214.645,130.405,13.993,-98.439,4.659,7.668,8.325,2.564,.064,.085,.175,68.378,-50.763,-71.521,2.826,27.625,16.681,.137,66.953
 4384.500,250.949,161.865,9.062,-101.507,3.985,6.178,8.329,2.539,.061,.100,.244,74.164,-48.504,-74.593,2.882,10.627,8.387,.159,69.978
 4385.000,293.134,196.758,10.347,-105.000,3.411,5.082,8.320,2.523,.063,.109,.288,65.517,-48.900,-78.088,2.926,7.391,7.090,.169,71.344
 4385.500,343.837,231.907,10.825,-108.511,2.908,4.312,8.321,2.515,.070,.114,.304,55.638,-52.966,-81.602,2.942,7.094,6.844,.167,71.110
 4386.000,388.997,261.158,11.331,-111.631,2.571,3.829,8.332,2.511,.079,.116,.303,46.825,-57.912,-84.726,2.931,7.304,6.927,.159,70.059
 4386.500,427.593,282.810,11.750,-114.048,2.339,3.536,8.343,2.509,.084,.117,.299,43.290,-62.450,-87.145,2.919,7.269,6.933,.152,69.026
 4387.000,455.882,299.126,11.926,-115.566,2.194,3.343,8.400,2.507,.087,.118,.287,41.352,-65.679,-88.666,2.900,7.167,6.867,.148,68.506
 4387.500,471.317,310.507,12.207,-116.080,2.122,3.220,8.451,2.504,.087,.121,.279,39.387,-67.368,-89.183,2.884,7.101,6.811,.148,68.494
 4388.000,476.156,316.327,12.012,-115.509,2.100,3.161,8.486,2.500,.084,.123,.276,36.245,-67.898,-88.615,2.876,7.108,6.816,.149,68.629
 4388.500,469.534,316.828,11.511,-113.771,2.130,3.156,8.556,2.502,.081,.121,.271,41.125,-67.387,-86.879,2.874,7.136,6.793,.150,68.698
 4389.000,456.160,312.419,11.892,-110.785,2.192,3.201,8.608,2.512,.079,.116,.264,42.222,-66.200,-83.897,2.872,7.350,6.913,.150,68.700
 4389.500,438.857,302.842,12.799,-106.531,2.279,3.302,8.661,2.529,.078,.106,.254,38.634,-64.370,-79.646,2.868,7.722,7.133,.148,68.394
 4390.000,414.089,286.810,12.076,-101.107,2.415,3.487,8.771,2.551,.077,.093,.233,37.524,-61.775,-74.225,2.856,9.022,7.541,.140,67.349
 4390.500,382.264,262.172,10.106,-94.794,2.616,3.814,8.822,2.581,.072,.075,.189,45.421,-59.672,-67.915,2.832,15.614,9.427,.126,65.305
 4391.000,342.232,227.987,9.683,-88.045,2.922,4.386,8.868,2.616,.066,.055,.140,59.698,-59.543,-61.169,2.815,29.360,13.283,.105,62.393
 4391.500,300.513,187.161,12.656,-81.395,3.328,5.343,8.917,2.646,.059,.037,.107,62.913,-62.079,-54.522,2.802,42.058,17.824,.083,59.281
 4392.000,257.492,146.166,20.103,-75.299,3.884,6.841,8.930,2.664,.053,.027,.087,51.227,-65.354,-48.429,2.784,48.287,20.813,.065,56.690
 4392.500,219.070,111.551,26.036,-69.993,4.565,8.965,8.964,2.665,.048,.026,.076,44.007,-68.171,-43.126,2.769,52.408,22.600,.052,54.856
 4393.000,186.316,86.275,29.470,-65.462,5.367,11.591,9.002,2.647,.045,.037,.072,45.739,-69.564,-38.597,2.754,67.443,27.798,.044,53.682
 4393.500,161.937,71.524,40.235,-61.524,6.175,13.981,9.045,2.596,.044,.067,.075,49.033,-69.293,-34.662,2.726,81.524,33.131,.043,53.540
 4394.000,148.920,69.821,51.177,-57.973,6.715,14.322,9.132,2.494,.047,.126,.087,53.257,-67.489,-31.115,2.687,69.790,28.781,.062,56.238
 4394.500,150.051,83.991,46.222,-54.690,6.664,11.906,9.339,2.366,.060,.201,.108,60.870,-64.611,-27.834,2.659,42.670,17.904,.112,63.278
 4395.000,160.695,113.064,27.893,-51.669,6.223,8.845,9.859,2.270,.083,.257,.138,80.680,-59.738,-24.816,2.849,17.359,8.138,.172,71.803
 4395.500,164.548,145.898,10.578,-48.990,6.077,6.854,9.893,2.238,.103,.276,.161,108.655,-51.391,-22.140,2.984,8.217,4.540,.206,76.604
 4396.000,160.597,164.506,7.586,-46.753,6.227,6.079,9.360,2.269,.107,.258,.166,112.551,-44.437,-19.906,3.000,27.106,11.918,.199,75.687
 4396.500,160.397,160.365,19.820,-45.021,6.234,6.236,9.333,2.353,.095,.209,.157,100.674,-43.708,-18.177,3.000,68.371,30.193,.162,70.395
 4397.000,165.846,143.206,30.627,-43.803,6.030,6.983,9.390,2.461,.075,.146,.136,94.829,-45.590,-16.961,2.958,69.999,32.279,.122,64.708
 4397.500,174.194,130.432,21.914,-43.065,5.741,7.667,9.454,2.548,.060,.095,.116,81.432,-45.169,-16.227,2.857,39.449,18.449,.108,62.789
 4398.000,181.185,129.012,11.835,-42.756,5.519,7.751,9.483,2.582,.052,.075,.107,84.212,-40.716,-15.920,2.877,21.910,9.950,.121,64.603
 4398.500,178.232,132.526,10.440,-42.800,5.611,7.546,9.529,2.575,.048,.079,.107,100.564,-32.288,-15.968,3.000,27.463,11.043,.141,67.449
 4399.000,166.956,134.791,10.167,-43.084,5.990,7.419,9.600,2.553,.047,.092,.114,100.599,-22.763,-16.255,3.000,26.155,10.979,.156,69.526
 4399.500,156.589,136.679,8.210,-43.446,6.386,7.316,9.653,2.537,.047,.101,.123,87.754,-15.645,-16.620,2.903,15.689,8.075,.164,70.766
 4400.000,153.898,139.555,8.281,-43.701,6.498,7.166,9.674,2.537,.048,.101,.133,72.295,-12.692,-16.877,2.779,14.775,7.938,.170,71.572
 4400.500,158.681,142.099,9.040,-43.697,6.302,7.037,9.739,2.553,.050,.092,.145,70.906,-13.074,-16.877,2.795,15.695,8.365,.171,71.714
 4401.000,166.901,143.931,8.929,-43.369,5.992,6.948,9.763,2.573,.051,.080,.157,80.900,-14.613,-16.551,2.853,14.955,8.096,.169,71.345
 4401.500,178.092,146.751,8.903,-42.744,5.615,6.814,9.800,2.585,.049,.073,.171,94.580,-16.213,-15.929,2.956,16.151,8.623,.169,71.369
 4402.000,190.991,152.476,8.662,-41.921,5.236,6.558,9.840,2.583,.046,.074,.194,94.380,-17.020,-15.110,2.954,15.603,8.408,.176,72.369
 4402.500,202.671,161.904,7.672,-41.024,4.934,6.176,9.879,2.570,.044,.082,.220,89.202,-16.393,-14.215,2.923,12.549,7.082,.190,74.333
 4403.000,214.064,174.694,6.523,-40.171,4.672,5.724,9.934,2.557,.046,.089,.239,89.017,-15.024,-13.365,2.937,10.127,5.940,.207,76.812
 4403.500,228.444,189.535,5.801,-39.460,4.377,5.276,9.940,2.548,.050,.095,.254,93.707,-14.287,-12.657,2.957,9.155,5.280,.223,79.063
 4404.000,241.935,204.341,5.601,-38.958,4.133,4.894,9.942,2.540,.053,.100,.264,95.804,-14.159,-12.158,2.970,8.947,5.051,.233,80.508
 4404.500,256.125,217.567,5.630,-38.700,3.904,4.596,9.977,2.529,.051,.106,.271,94.128,-15.063,-11.903,2.970,9.068,4.996,.237,81.094
 4405.000,269.831,229.018,5.663,-38.696,3.706,4.366,10.029,2.516,.047,.113,.273,96.076,-16.500,-11.902,2.976,9.313,4.991,.238,81.177
 4405.500,278.718,238.810,5.638,-38.940,3.588,4.187,10.051,2.505,.043,.120,.267,97.992,-17.565,-12.149,2.983,9.030,5.075,.237,81.081
 4406.000,281.858,245.776,5.553,-39.430,3.548,4.069,10.124,2.496,.046,.125,.260,102.203,-18.282,-12.641,3.000,8.884,5.079,.235,80.752
 4406.500,277.260,247.142,5.433,-40.161,3.607,4.046,10.200,2.491,.056,.128,.254,101.803,-19.000,-13.376,3.000,8.251,5.057,.228,79.728
 4407.000,265.703,240.011,5.509,-41.127,3.764,4.167,10.170,2.497,.071,.124,.249,101.150,-20.523,-14.344,3.000,8.114,5.438,.213,77.569
 4407.500,250.879,224.008,6.254,-42.298,3.986,4.464,9.813,2.519,.086,.112,.244,93.110,-23.334,-15.519,2.945,11.050,6.730,.191,74.478
 4408.000,235.570,202.754,8.069,-43.626,4.245,4.932,9.630,2.549,.093,.094,.238,80.824,-26.676,-16.850,2.922,16.719,8.648,.168,71.332
 4408.500,222.399,181.709,10.685,-45.042,4.496,5.503,9.603,2.577,.092,.078,.225,76.939,-29.339,-18.269,2.914,21.154,9.952,.153,69.102
 4409.000,209.249,164.477,11.994,-46.472,4.779,6.080,9.604,2.589,.085,.071,.203,75.151,-29.812,-19.702,2.892,23.785,10.367,.147,68.307
 4409.500,195.314,151.936,11.265,-47.845,5.120,6.582,9.594,2.584,.075,.074,.186,70.274,-27.665,-21.077,2.857,23.556,10.725,.150,68.783
 4410.000,182.037,143.556,10.037,-49.094,5.493,6.966,9.594,2.569,.066,.083,.184,73.063,-23.703,-22.330,2.851,21.148,10.092,.158,69.865
 4410.500,171.546,138.696,9.183,-50.170,5.829,7.210,9.589,2.555,.062,.091,.189,76.338,-19.361,-23.408,2.856,19.093,8.973,.166,70.935
 4411.000,165.184,137.029,8.843,-51.033,6.054,7.298,9.589,2.545,.061,.097,.195,85.104,-15.866,-24.274,2.884,17.922,8.298,.172,71.797
 4411.500,163.038,138.052,8.665,-51.663,6.134,7.244,9.592,2.536,.062,.102,.200,89.867,-13.711,-24.907,2.919,17.151,7.796,.177,72.503
 4412.000,164.596,140.733,8.333,-52.051,6.076,7.106,9.589,2.528,.062,.106,.198,83.567,-12.847,-25.298,2.876,15.824,7.279,.181,73.060
 4412.500,168.582,144.004,8.086,-52.195,5.932,6.944,9.589,2.525,.064,.108,.192,82.256,-12.907,-25.445,2.866,13.114,6.887,.183,73.458
 4413.000,173.416,147.295,8.018,-52.097,5.766,6.789,9.591,2.528,.069,.107,.189,78.990,-13.464,-25.350,2.851,11.120,6.604,.185,73.688
 4413.500,178.297,150.505,8.050,-51.764,5.609,6.644,9.581,2.534,.076,.103,.188,79.934,-14.246,-25.020,2.856,10.922,6.840,.186,73.821
 4414.000,182.866,153.749,8.106,-51.212,5.469,6.504,9.576,2.541,.080,.099,.196,80.880,-15.030,-24.471,2.870,11.280,7.243,.188,74.035
 4414.500,187.191,157.079,8.056,-50.473,5.342,6.366,9.575,2.548,.080,.095,.214,90.774,-15.715,-23.735,2.926,14.204,7.192,.190,74.382
 4415.000,190.927,160.338,7.889,-49.604,5.238,6.237,9.561,2.554,.075,.091,.226,93.892,-16.219,-22.869,2.951,15.475,7.305,.192,74.701
 4415.500,194.604,163.398,7.796,-48.691,5.139,6.120,9.519,2.560,.069,.088,.225,94.526,-16.717,-21.959,2.956,14.825,7.231,.193,74.764
 4416.000,198.507,166.541,7.840,-47.842,5.038,6.004,9.521,2.568,.064,.083,.216,100.195,-17.297,-21.113,2.991,13.948,7.041,.191,74.468
 4416.500,202.872,170.272,7.848,-47.172,4.929,5.873,9.497,2.577,.062,.078,.212,100.202,-17.932,-20.446,2.997,13.590,6.825,.187,74.021
 4417.000,207.019,174.757,7.839,-46.781,4.831,5.722,9.489,2.585,.062,.073,.221,103.684,-18.362,-20.058,3.000,13.091,6.781,.186,73.873
 4417.500,209.917,179.503,7.769,-46.736,4.764,5.571,9.483,2.587,.064,.072,.234,107.972,-18.397,-20.016,3.000,12.319,6.576,.189,74.280
 4418.000,210.160,183.116,7.463,-47.063,4.758,5.461,9.486,2.583,.068,.074,.242,106.371,-18.246,-20.345,2.997,12.004,6.472,.193,74.822
 4418.500,205.811,183.210,7.055,-47.745,4.859,5.458,9.492,2.578,.075,.077,.241,103.165,-18.767,-21.030,2.992,11.689,6.214,.190,74.452
 4419.000,196.305,176.871,6.763,-48.721,5.094,5.654,9.327,2.579,.084,.077,.231,94.900,-21.301,-22.009,2.959,13.079,6.609,.177,72.505
 4419.500,183.518,162.721,7.829,-49.886,5.449,6.146,9.191,2.587,.088,.072,.206,69.092,-26.222,-23.178,2.878,27.568,11.002,.153,69.143
 4420.000,170.043,143.262,12.563,-51.094,5.881,6.980,9.186,2.599,.086,.065,.170,47.496,-32.057,-24.388,2.825,48.710,17.289,.124,65.032
 4420.500,156.781,123.147,18.317,-52.178,6.378,8.120,9.156,2.609,.077,.059,.139,37.746,-36.682,-25.475,2.794,46.296,16.965,.098,61.334
 4421.000,141.995,105.207,20.992,-52.990,7.043,9.505,9.131,2.613,.065,.056,.115,33.310,-38.427,-26.290,2.772,43.043,16.147,.081,58.958
 4421.500,126.087,89.714,21.707,-53.445,7.931,11.146,9.079,2.614,.054,.056,.099,34.716,-37.229,-26.748,2.756,48.695,17.991,.074,57.948
 4422.000,109.279,76.545,21.738,-53.538,9.151,13.064,9.038,2.617,.047,.054,.088,34.546,-33.541,-26.844,2.747,50.372,18.536,.074,57.914
 4422.500,94.371,66.262,22.457,-53.330,10.596,15.092,9.034,2.628,.046,.048,.082,32.007,-28.868,-26.639,2.748,49.348,17.876,.077,58.360
 4423.000,83.105,59.187,22.762,-52.913,12.033,16.896,9.003,2.644,.049,.039,.079,33.098,-24.597,-26.224,2.756,44.984,16.334,.080,58.829
 4423.500,75.977,54.865,22.442,-52.372,13.162,18.226,8.981,2.658,.053,.031,.078,36.612,-21.692,-25.687,2.764,40.740,15.311,.082,59.043
 4424.000,71.403,52.435,23.539,-51.774,14.005,19.071,8.953,2.665,.056,.026,.077,39.097,-20.057,-25.092,2.769,38.925,15.821,.081,58.962
 4424.500,68.416,51.063,24.246,-51.161,14.616,19.584,8.930,2.670,.060,.023,.076,42.269,-20.208,-24.481,2.772,39.094,15.660,.079,58.629
 4425.000,65.012,49.840,22.219,-50.559,15.382,20.064,8.927,2.675,.063,.021,.075,48.775,-22.697,-23.883,2.778,37.647,14.507,.074,57.928
 4425.500,60.731,47.592,22.000,-49.982,16.466,21.012,8.932,2.677,.063,.019,.074,52.155,-28.120,-23.308,2.779,43.113,16.401,.065,56.723
 4426.000,56.165,43.655,33.235,-49.425,17.805,22.907,8.938,2.677,.060,.020,.070,47.722,-34.926,-22.754,2.773,61.772,22.128,.055,55.247
 4426.500,52.361,38.697,62.954,-48.872,19.098,25.842,8.926,2.677,.059,.019,.064,41.396,-40.420,-22.204,2.764,76.749,24.994,.047,54.125
 4427.000,49.471,34.224,87.728,-48.305,20.214,29.220,8.935,2.684,.059,.015,.059,34.774,-42.424,-21.640,2.761,83.050,25.497,.044,53.750
 4427.500,46.909,31.316,71.723,-47.721,21.318,31.933,8.928,2.695,.061,.009,.055,39.414,-40.128,-21.060,2.766,67.339,21.228,.045,53.911
 4428.000,43.802,29.763,43.705,-47.134,22.830,33.599,8.927,2.701,.060,.005,.054,45.308,-34.262,-20.476,2.771,47.810,16.681,.047,54.194
 4428.500,40.411,28.563,38.238,-46.568,24.746,35.011,8.938,2.695,.055,.009,.055,48.061,-27.712,-19.912,2.769,48.327,16.537,.048,54.310
 4429.000,37.790,27.213,45.463,-46.045,26.462,36.747,8.939,2.680,.049,.017,.054,46.518,-23.602,-19.392,2.757,53.102,17.195,.047,54.208
 4429.500,35.987,26.029,51.801,-45.576,27.788,38.419,8.931,2.665,.043,.026,.052,45.061,-21.928,-18.926,2.742,51.991,17.805,.047,54.117
 4430.000,34.711,25.339,53.747,-45.162,28.810,39.465,8.931,2.656,.042,.032,.050,43.796,-21.156,-18.515,2.734,51.767,20.629,.047,54.162
 4430.500,33.059,24.946,48.791,-44.790,30.249,40.087,8.929,2.654,.043,.033,.050,43.245,-19.837,-18.146,2.731,46.968,25.062,.047,54.196
 4431.000,30.335,24.425,44.769,-44.436,32.966,40.942,8.924,2.654,.045,.033,.049,45.644,-17.601,-17.794,2.730,42.924,27.623,.047,54.090
 4431.500,27.154,23.600,50.664,-44.076,36.827,42.373,8.927,2.651,.044,.034,.048,46.877,-15.402,-17.437,2.728,48.681,30.154,.045,53.808
 4432.000,24.284,22.607,61.438,-43.696,41.179,44.235,8.929,2.647,.042,.037,.046,40.746,-13.695,-17.061,2.722,62.617,32.711,.042,53.400
 4432.500,22.410,21.659,67.418,-43.300,44.624,46.171,8.934,2.645,.042,.038,.046,36.720,-12.813,-16.668,2.720,78.121,32.040,.039,52.996
 4433.000,21.635,20.837,65.420,-42.902,46.222,47.992,8.941,2.651,.044,.034,.045,35.084,-12.772,-16.272,2.723,83.536,32.231,.037,52.715
 4433.500,21.726,20.059,65.153,-42.516,46.028,49.852,8.950,2.663,.047,.027,.045,37.045,-13.357,-15.890,2.731,83.184,32.009,.036,52.646
 4434.000,22.493,19.266,66.814,-42.151,44.459,51.905,8.966,2.673,.047,.021,.045,35.484,-14.358,-15.528,2.739,82.193,28.775,.037,52.799
 4434.500,24.187,18.631,63.758,-41.805,41.345,53.674,8.988,2.673,.042,.021,.046,32.186,-15.948,-15.184,2.739,80.652,26.132,.040,53.127
 4435.000,27.042,18.632,62.618,-41.469,36.979,53.672,9.002,2.663,.037,.028,.048,35.745,-17.670,-14.851,2.735,85.637,28.209,.044,53.683
 4435.500,31.760,20.109,59.951,-41.135,31.486,49.729,9.043,2.650,.033,.035,.052,37.219,-19.177,-14.520,2.730,87.706,30.693,.051,54.692
 4436.000,39.278,24.387,45.304,-40.801,25.459,41.006,9.092,2.641,.034,.040,.059,39.501,-19.918,-14.189,2.733,72.760,26.588,.063,56.447
 4436.500,50.805,33.224,26.823,-40.474,19.683,30.099,9.118,2.634,.038,.044,.070,51.615,-19.523,-13.865,2.743,46.515,18.223,.083,59.181
 4437.000,66.821,48.664,18.141,-40.180,14.965,20.549,9.131,2.622,.042,.052,.087,65.281,-17.562,-13.574,2.762,38.838,14.692,.109,62.987
 4437.500,89.496,72.432,13.660,-39.962,11.174,13.806,9.197,2.595,.045,.067,.112,77.023,-15.345,-13.359,2.801,32.701,11.769,.143,67.742
 4438.000,115.826,104.313,9.784,-39.876,8.634,9.587,9.314,2.552,.048,.093,.152,88.460,-12.168,-13.276,2.909,20.957,8.457,.180,73.028
 4438.500,142.594,140.774,6.579,-39.978,7.013,7.104,9.448,2.501,.056,.122,.214,102.541,-8.782,-13.381,3.000,10.638,5.730,.216,78.113
 4439.000,164.143,174.586,5.376,-40.304,6.092,5.728,9.514,2.462,.071,.145,.243,110.852,-6.427,-13.710,3.000,7.834,4.634,.242,81.714
 4439.500,176.995,197.316,5.169,-40.849,5.650,5.068,9.537,2.448,.087,.153,.244,105.140,-7.153,-14.258,3.000,6.385,4.165,.246,82.240
 4440.000,183.836,203.843,5.782,-41.553,5.440,4.906,9.410,2.459,.096,.147,.231,96.036,-11.870,-14.965,2.968,6.712,4.400,.226,79.541
 4440.500,188.710,195.084,8.235,-42.311,5.299,5.126,9.397,2.487,.089,.130,.216,89.687,-18.725,-15.726,2.918,12.378,6.870,.197,75.337
 4441.000,191.277,178.106,11.313,-42.993,5.228,5.615,9.414,2.520,.071,.111,.198,84.378,-24.507,-16.411,2.879,20.290,10.966,.171,71.691
 4441.500,189.365,161.505,12.601,-43.485,5.281,6.192,9.433,2.550,.053,.094,.179,75.426,-26.975,-16.906,2.841,23.849,12.927,.159,70.046
 4442.000,183.533,149.883,11.736,-43.728,5.449,6.672,9.470,2.572,.044,.080,.159,72.828,-25.839,-17.151,2.824,20.744,11.474,.162,70.385
 4442.500,174.901,143.563,9.917,-43.733,5.718,6.966,9.473,2.587,.045,.072,.144,80.081,-21.894,-17.159,2.840,14.881,8.810,.169,71.459
 4443.000,166.917,141.808,8.560,-43.579,5.991,7.052,9.463,2.594,.052,.068,.149,84.225,-16.953,-17.008,2.877,12.399,7.696,.176,72.460
 4443.500,166.950,145.127,8.382,-43.373,5.990,6.891,9.460,2.593,.061,.068,.181,84.709,-13.698,-16.805,2.888,12.646,7.843,.184,73.588
 4444.000,175.654,154.318,8.134,-43.210,5.693,6.480,9.460,2.588,.072,.071,.218,89.733,-12.621,-16.645,2.932,11.376,6.999,.195,75.079
 4444.500,188.604,168.163,7.057,-43.147,5.302,5.947,9.469,2.583,.081,.074,.230,90.497,-12.602,-16.586,2.944,8.791,5.507,.206,76.656
 4445.000,202.719,183.229,6.374,-43.200,4.933,5.458,9.452,2.576,.086,.078,.238,91.831,-13.113,-16.642,2.950,8.110,5.037,.215,77.968
 4445.500,217.115,196.181,6.434,-43.350,4.606,5.097,9.463,2.565,.087,.085,.252,98.075,-14.288,-16.795,2.984,9.532,5.344,.221,78.744
 4446.000,227.441,205.755,6.461,-43.564,4.397,4.860,9.454,2.557,.092,.090,.263,100.982,-15.521,-17.011,3.000,9.910,5.464,.222,78.900
 4446.500,234.307,211.501,6.343,-43.814,4.268,4.728,9.450,2.565,.104,.085,.266,101.720,-16.966,-17.264,3.000,9.575,5.299,.220,78.642
 4447.000,238.059,212.356,6.481,-44.100,4.201,4.709,9.445,2.586,.119,.072,.261,102.973,-18.663,-17.552,3.000,9.304,5.348,.215,77.914
 4447.500,237.594,208.245,6.888,-44.453,4.209,4.802,9.440,2.606,.123,.061,.258,96.664,-20.305,-17.909,3.012,9.652,5.851,.205,76.570
 4448.000,236.299,201.375,7.477,-44.924,4.232,4.966,9.432,2.601,.113,.064,.261,87.918,-22.081,-18.383,2.992,10.785,6.551,.194,74.909
 4448.500,236.177,195.166,8.057,-45.550,4.234,5.124,9.452,2.550,.089,.093,.263,90.303,-23.768,-19.012,2.966,11.826,6.911,.183,73.388
 4449.000,236.573,192.923,8.364,-46.337,4.227,5.183,9.587,2.436,.061,.160,.269,97.455,-24.662,-19.801,2.981,12.353,6.951,.179,72.794
 4449.500,240.304,197.409,8.572,-47.242,4.161,5.066,9.905,2.268,.041,.259,.285,94.114,-24.723,-20.710,2.974,12.189,6.614,.193,74.876
 4450.000,247.864,209.868,8.145,-48.194,4.035,4.765,10.666,2.103,.040,.355,.302,95.962,-23.844,-21.664,2.983,9.139,5.496,.232,80.301
 4450.500,252.430,227.087,6.701,-49.115,3.961,4.404,11.557,1.995,.053,.418,.301,107.820,-21.739,-22.588,2.990,5.466,4.321,.274,86.290
 4451.000,250.865,239.792,5.416,-49.966,3.986,4.170,11.740,1.956,.070,.441,.292,104.266,-21.182,-23.443,2.986,4.506,3.579,.297,89.483
 4451.500,244.085,238.537,5.031,-50.778,4.097,4.192,10.309,1.976,.081,.429,.289,94.822,-28.981,-24.257,2.978,4.076,3.137,.285,87.854
 4452.000,229.129,221.516,5.303,-51.647,4.364,4.514,9.694,2.040,.085,.392,.279,93.808,-47.903,-25.129,2.969,4.759,3.398,.233,80.400
 4452.500,209.243,193.133,6.999,-52.695,4.779,5.178,9.343,2.131,.085,.339,.257,94.840,-71.453,-26.180,2.958,13.144,5.837,.162,70.357
 4453.000,192.586,158.981,20.535,-54.005,5.193,6.290,8.697,2.235,.082,.278,.235,88.397,-93.290,-27.494,2.917,31.722,12.229,.106,62.542
 4453.500,172.978,125.158,77.189,-55.572,5.781,7.990,8.612,2.342,.078,.215,.199,65.190,-108.787,-29.063,2.736,24.949,13.001,.073,57.880
 4454.000,148.671,96.510,163.541,-57.298,6.726,10.362,8.609,2.436,.075,.160,.149,41.473,-116.387,-30.792,2.705,11.731,10.058,.056,55.444
 4454.500,121.199,73.826,205.552,-59.040,8.251,13.545,8.609,2.501,.075,.122,.119,27.765,-115.990,-32.537,2.707,9.684,9.473,.049,54.469
 4455.000,92.317,55.101,209.238,-60.673,10.832,18.149,8.609,2.541,.077,.099,.103,23.594,-107.726,-34.173,2.714,12.367,11.221,.046,53.946
 4455.500,64.534,39.237,184.766,-62.134,15.496,25.486,8.608,2.573,.077,.080,.091,25.277,-92.035,-35.637,2.722,31.807,20.144,.040,53.217
 4456.000,46.290,27.147,130.109,-63.431,21.603,36.837,8.610,2.604,.076,.062,.078,29.688,-75.012,-36.937,2.728,71.317,34.964,.034,52.341
 4456.500,36.722,19.589,101.988,-64.612,27.232,51.050,8.608,2.635,.073,.044,.064,30.486,-61.836,-38.121,2.733,94.503,47.852,.029,51.653
 4457.000,32.406,15.766,121.710,-65.730,30.858,63.427,8.569,2.661,.070,.029,.054,32.500,-54.600,-39.242,2.739,97.918,52.373,.027,51.272
 4457.500,30.673,14.254,122.905,-66.829,32.602,70.157,8.493,2.679,.066,.018,.047,33.078,-52.442,-40.344,2.745,95.186,45.813,.025,51.040
 4458.000,30.059,13.990,110.718,-67.947,33.268,71.478,8.476,2.686,.063,.014,.043,31.260,-53.473,-41.465,2.745,96.527,47.308,.023,50.795
 4458.500,29.060,14.291,135.786,-69.119,34.412,69.975,8.461,2.682,.060,.016,.040,29.173,-54.745,-42.640,2.738,99.563,55.871,.021,50.533
 4459.000,27.519,14.667,174.448,-70.378,36.339,68.179,8.455,2.667,.056,.025,.038,28.701,-54.658,-43.901,2.726,100.205,56.667,.020,50.371
 4459.500,25.939,14.825,170.827,-71.734,38.552,67.454,8.431,2.648,.052,.036,.038,28.960,-53.050,-45.260,2.712,99.514,52.600,.021,50.433
 4460.000,24.644,14.636,136.585,-73.173,40.577,68.327,8.382,2.633,.049,.045,.040,30.557,-50.922,-46.702,2.706,98.270,51.890,.023,50.766
 4460.500,23.632,14.120,120.676,-74.657,42.315,70.824,8.351,2.627,.052,.049,.043,32.868,-49.755,-48.189,2.706,87.494,46.028,.027,51.306
 4461.000,22.838,13.502,148.702,-76.134,43.786,74.062,8.331,2.628,.059,.048,.048,33.102,-50.221,-49.669,2.710,48.809,27.138,.031,51.882
 4461.500,22.422,13.087,185.083,-77.542,44.599,76.411,8.297,2.633,.068,.045,.053,28.209,-51.684,-51.081,2.719,16.706,12.622,.035,52.465
 4462.000,22.213,13.039,198.443,-78.814,45.018,76.693,8.278,2.638,.076,.042,.058,27.212,-52.285,-52.355,2.729,10.912,10.327,.040,53.161
 4462.500,21.974,13.314,186.253,-79.881,45.509,75.111,8.272,2.641,.083,.041,.065,29.346,-50.712,-53.425,2.738,10.705,10.061,.046,54.049
 4463.000,21.635,13.734,154.080,-80.676,46.221,72.813,8.272,2.640,.089,.041,.073,30.704,-47.013,-54.223,2.746,9.286,8.982,.054,55.179
 4463.500,21.245,14.131,126.622,-81.147,47.069,70.765,8.276,2.633,.090,.045,.084,29.280,-42.314,-54.697,2.752,8.152,8.269,.063,56.409
 4464.000,20.893,14.411,114.530,-81.260,47.863,69.393,8.281,2.621,.088,.052,.089,26.810,-38.258,-54.813,2.750,7.966,8.136,.069,57.257
 4464.500,20.621,14.512,110.958,-81.004,48.494,68.908,8.318,2.611,.083,.058,.085,25.719,-36.246,-54.560,2.740,8.148,8.287,.069,57.235
 4465.000,20.283,14.407,113.331,-80.397,49.302,69.413,8.393,2.609,.078,.059,.075,25.649,-36.678,-53.956,2.728,10.218,9.771,.062,56.246
 4465.500,19.765,14.161,121.036,-79.474,50.595,70.617,8.443,2.615,.074,.056,.065,26.224,-39.124,-53.035,2.720,20.894,15.498,.051,54.674
 4466.000,19.263,13.982,143.253,-78.275,51.913,71.520,8.460,2.627,.072,.049,.057,25.697,-42.829,-51.840,2.719,31.276,20.219,.040,53.183
 4466.500,18.760,14.030,190.822,-76.839,53.305,71.277,8.467,2.647,.076,.037,.049,26.963,-46.067,-50.407,2.725,22.714,16.527,.033,52.222
 4467.000,17.975,14.059,218.195,-75.198,55.633,71.131,8.441,2.675,.083,.021,.044,29.389,-46.724,-48.768,2.738,18.930,14.007,.030,51.743
 4467.500,17.001,13.562,209.446,-73.387,58.819,73.733,8.430,2.701,.086,.005,.041,31.741,-44.163,-46.960,2.753,42.336,20.800,.028,51.484
 4468.000,16.350,12.462,177.765,-71.456,61.162,80.242,8.430,2.713,.080,-.002,.039,32.953,-39.680,-45.032,2.760,82.436,34.929,.027,51.255
 4468.500,15.841,11.425,142.002,-69.474,63.126,87.528,8.429,2.710,.068,.000,.037,35.626,-34.004,-43.054,2.756,96.246,38.197,.025,51.046
 4469.000,15.371,11.124,108.485,-67.523,65.058,89.898,8.427,2.700,.057,.006,.034,37.899,-28.765,-41.105,2.745,97.831,37.233,.024,50.958
 4469.500,15.290,11.409,107.082,-65.682,65.402,87.649,8.433,2.688,.051,.013,.032,34.783,-26.543,-39.267,2.734,99.752,39.977,.025,50.972
 4470.000,15.226,11.771,134.681,-64.017,65.678,84.951,8.433,2.675,.047,.021,.032,29.537,-26.552,-37.605,2.724,99.591,41.692,.024,50.938
 4470.500,14.909,12.005,141.368,-62.563,67.075,83.297,8.427,2.664,.044,.027,.032,27.353,-26.976,-36.154,2.716,99.285,40.071,.024,50.839
 4471.000,14.669,12.092,133.717,-61.326,68.170,82.697,8.444,2.660,.043,.029,.033,26.806,-27.747,-34.920,2.714,100.007,41.099,.023,50.759
 4471.500,14.359,12.004,140.985,-60.283,69.640,83.308,8.437,2.665,.046,.026,.032,29.239,-28.265,-33.880,2.717,100.067,41.204,.023,50.706
 4472.000,13.928,11.724,150.388,-59.397,71.797,85.295,8.427,2.674,.050,.021,.031,33.719,-28.396,-32.997,2.722,99.637,40.204,.022,50.648
 4472.500,13.691,11.338,156.338,-58.623,73.040,88.199,8.428,2.684,.054,.015,.030,34.368,-28.928,-32.226,2.728,96.614,37.441,.022,50.549
 4473.000,13.742,11.034,156.667,-57.911,72.770,90.632,8.428,2.691,.058,.011,.030,37.951,-29.951,-31.517,2.735,90.757,36.880,.021,50.451
 4473.500,13.857,10.990,160.174,-57.218,72.163,90.992,8.428,2.696,.062,.008,.032,40.512,-30.502,-30.827,2.740,92.422,40.213,.021,50.464
 4474.000,14.136,11.351,171.977,-56.511,70.742,88.100,8.445,2.695,.062,.009,.033,41.365,-30.487,-30.123,2.742,98.695,44.869,.022,50.656
 4474.500,14.574,12.228,166.501,-55.780,68.617,81.780,8.450,2.688,.059,.013,.036,51.208,-30.174,-29.395,2.739,98.076,44.182,.025,50.983
 4475.000,15.025,13.473,111.452,-55.039,66.555,74.222,8.454,2.676,.054,.020,.039,76.045,-31.023,-28.656,2.782,85.136,34.263,.027,51.295
 4475.500,14.941,14.487,88.765,-54.309,66.930,69.027,8.456,2.661,.047,.028,.041,103.641,-34.079,-27.930,2.940,71.467,28.193,.028,51.491
 4476.000,14.556,14.610,167.426,-53.605,68.699,68.447,8.449,2.646,.038,.037,.043,91.637,-39.715,-27.229,2.933,81.168,31.406,.028,51.500
 4476.500,14.366,13.797,266.432,-52.917,69.610,72.481,8.452,2.635,.032,.044,.042,62.410,-46.218,-26.544,2.720,95.556,39.676,.026,51.232
 4477.000,14.378,12.644,301.135,-52.216,69.550,79.092,8.457,2.638,.030,.042,.039,40.821,-51.165,-25.846,2.709,98.597,41.888,.023,50.776
 4477.500,14.541,11.669,296.668,-51.470,68.771,85.696,8.457,2.654,.034,.033,.036,33.047,-53.694,-25.102,2.713,98.118,38.966,.020,50.314
 4478.000,14.546,10.887,285.930,-50.655,68.749,91.850,8.463,2.673,.038,.021,.033,32.868,-53.275,-24.290,2.724,98.647,40.315,.017,49.928
 4478.500,13.960,10.144,266.385,-49.770,71.633,98.579,8.466,2.681,.040,.017,.029,31.104,-49.250,-23.409,2.725,99.978,43.691,.015,49.668
 4479.000,13.331,9.545,232.624,-48.829,75.013,104.769,8.465,2.672,.039,.022,.026,34.683,-43.418,-22.470,2.715,99.988,43.671,.015,49.562
 4479.500,13.091,9.364,201.724,-47.850,76.387,106.795,8.486,2.659,.037,.030,.024,36.702,-37.255,-21.494,2.706,99.906,43.579,.015,49.614
 4480.000,12.904,9.739,166.574,-46.859,77.496,102.675,8.525,2.654,.038,.033,.022,39.225,-29.946,-20.506,2.702,98.224,42.271,.016,49.815
 4480.500,13.002,10.681,128.442,-45.881,76.909,93.626,8.553,2.658,.040,.030,.022,35.952,-22.493,-19.531,2.704,90.223,38.804,.018,50.107
 4481.000,13.863,12.181,95.836,-44.949,72.133,82.098,8.599,2.664,.043,.027,.022,31.396,-16.853,-18.602,2.706,81.971,37.932,.021,50.424
 4481.500,14.986,14.198,80.937,-44.100,66.730,70.434,8.623,2.665,.045,.026,.023,30.931,-12.169,-17.755,2.707,79.097,39.664,.023,50.759
 4482.000,16.483,16.644,72.527,-43.366,60.668,60.082,8.616,2.661,.044,.029,.024,35.200,-9.167,-17.025,2.707,72.234,36.112,.027,51.262
 4482.500,18.450,19.329,65.671,-42.776,54.201,51.737,8.625,2.651,.043,.034,.027,40.226,-8.236,-16.438,2.706,69.131,31.439,.033,52.102
 4483.000,19.929,21.822,55.200,-42.350,50.179,45.826,8.650,2.637,.041,.043,.032,41.463,-8.474,-16.014,2.703,65.897,28.838,.040,53.190
 4483.500,20.887,23.400,40.045,-42.094,47.876,42.735,8.686,2.615,.038,.056,.039,45.891,-12.192,-15.762,2.699,49.811,21.236,.047,54.217
 4484.000,21.980,23.380,47.148,-42.000,45.496,42.771,8.714,2.587,.036,.072,.047,47.667,-20.603,-15.670,2.693,44.681,20.328,.053,55.070
 4484.500,23.808,22.012,103.024,-42.042,42.003,45.429,8.742,2.560,.036,.088,.058,39.735,-30.748,-15.716,2.685,59.246,30.638,.060,55.921
 4485.000,27.329,21.006,158.230,-42.183,36.591,47.604,8.763,2.542,.036,.098,.069,28.838,-39.506,-15.860,2.684,56.944,35.328,.066,56.880
 4485.500,33.776,22.656,134.774,-42.377,29.607,44.138,8.762,2.535,.036,.102,.079,27.466,-45.252,-16.056,2.689,53.572,36.110,.073,57.891
 4486.000,43.050,28.680,63.833,-42.573,23.229,34.867,8.792,2.537,.034,.101,.084,39.998,-45.895,-16.256,2.699,54.465,29.474,.081,58.916
 4486.500,55.575,40.081,27.487,-42.724,17.994,24.949,8.810,2.544,.033,.097,.089,56.922,-41.748,-16.409,2.717,47.820,21.767,.092,60.546
 4487.000,72.121,57.665,24.224,-42.789,13.866,17.342,8.853,2.549,.038,.094,.095,68.355,-34.778,-16.477,2.736,56.227,25.649,.115,63.723
 4487.500,89.269,81.159,18.334,-42.745,11.202,12.322,8.959,2.548,.049,.095,.101,81.854,-25.749,-16.436,2.860,46.418,22.074,.145,68.065
 4488.000,105.227,106.412,9.408,-42.602,9.503,9.397,9.034,2.545,.061,.097,.107,98.918,-16.899,-16.296,2.991,20.016,10.513,.174,72.066
 4488.500,119.932,126.905,6.709,-42.411,8.338,7.880,9.098,2.543,.070,.097,.114,114.252,-10.630,-16.108,3.000,10.111,6.077,.191,74.481
 4489.000,134.601,140.180,7.866,-42.267,7.429,7.134,9.142,2.546,.072,.096,.128,110.820,-8.881,-15.967,3.000,11.698,6.703,.194,74.964
 4489.500,149.742,149.492,9.746,-42.296,6.678,6.689,9.186,2.548,.072,.095,.145,104.654,-10.874,-15.999,3.000,14.537,8.022,.192,74.624
 4490.000,163.103,158.031,9.507,-42.625,6.131,6.328,9.285,2.549,.072,.094,.154,103.122,-13.663,-16.331,3.000,13.516,7.821,.191,74.538
 4490.500,171.661,163.953,7.818,-43.337,5.825,6.099,9.302,2.552,.075,.092,.158,97.626,-15.603,-17.046,2.980,10.444,6.500,.190,74.435
 4491.000,171.724,163.642,7.564,-44.436,5.823,6.111,9.335,2.557,.075,.090,.163,88.379,-16.481,-18.148,2.908,11.310,6.610,.185,73.665
 4491.500,167.418,157.469,8.951,-45.829,5.973,6.350,9.413,2.557,.071,.089,.154,73.362,-17.543,-19.544,2.812,15.263,8.108,.174,72.077
 4492.000,164.278,149.424,10.719,-47.357,6.087,6.692,9.472,2.550,.063,.094,.134,65.762,-19.236,-21.074,2.773,18.933,9.415,.161,70.331
 4492.500,163.770,143.021,11.441,-48.841,6.106,6.992,9.514,2.535,.053,.102,.120,64.635,-20.798,-22.561,2.750,19.794,9.698,.153,69.212
 4493.000,164.194,139.253,10.975,-50.135,6.090,7.181,9.569,2.519,.044,.112,.115,65.149,-21.307,-23.859,2.738,19.644,9.496,.151,68.850
 4493.500,164.617,137.553,10.370,-51.161,6.075,7.270,9.618,2.507,.038,.119,.117,70.743,-20.698,-24.887,2.746,18.819,9.273,.152,68.983
 4494.000,166.002,137.833,9.957,-51.916,6.024,7.255,9.671,2.503,.037,.121,.125,67.973,-19.632,-25.646,2.744,17.400,9.177,.155,69.412
 4494.500,169.891,140.865,9.577,-52.480,5.886,7.099,9.740,2.509,.040,.118,.136,67.777,-18.788,-26.213,2.757,16.664,8.787,.159,70.037
 4495.000,177.042,147.379,9.097,-52.992,5.648,6.785,9.786,2.521,.045,.111,.147,73.034,-18.393,-26.727,2.787,15.638,8.157,.166,70.924
 4495.500,187.694,157.887,8.662,-53.606,5.328,6.334,9.857,2.527,.049,.107,.156,78.869,-18.422,-27.344,2.824,13.621,7.619,.176,72.386
 4496.000,201.089,172.253,8.080,-54.422,4.973,5.805,9.931,2.518,.052,.112,.162,86.320,-18.799,-28.163,2.893,12.842,7.170,.191,74.565
 4496.500,211.651,188.266,7.123,-55.405,4.725,5.312,9.994,2.494,.053,.126,.174,84.205,-18.983,-29.149,2.877,12.790,6.723,.209,77.070
 4497.000,217.556,201.543,6.556,-56.369,4.596,4.962,10.081,2.468,.056,.141,.194,84.202,-19.459,-30.116,2.877,14.404,7.221,.223,79.060
 4497.500,219.688,207.950,7.491,-57.032,4.552,4.809,10.126,2.458,.060,.147,.207,88.793,-20.718,-30.782,2.911,18.616,9.281,.226,79.507
 4498.000,217.898,206.183,8.443,-57.150,4.589,4.850,10.151,2.469,.065,.141,.196,91.220,-22.377,-30.902,2.919,19.427,9.736,.215,77.909
 4498.500,214.671,197.500,8.163,-56.622,4.658,5.063,10.221,2.493,.067,.127,.176,82.523,-24.356,-30.378,2.865,15.559,8.411,.194,74.923
 4499.000,211.586,184.116,8.974,-55.524,4.726,5.431,10.257,2.516,.064,.113,.166,75.139,-26.543,-29.283,2.810,16.917,8.986,.172,71.899
 4499.500,205.339,168.928,10.558,-54.037,4.870,5.920,10.279,2.531,.059,.105,.162,73.816,-27.869,-27.799,2.808,20.545,10.170,.158,69.876
 4500.000,195.648,154.790,11.066,-52.346,5.111,6.460,10.307,2.537,.053,.101,.159,67.569,-27.756,-26.111,2.794,20.589,10.293,.153,69.103
 4500.500,184.427,143.238,10.893,-50.571,5.422,6.981,10.372,2.539,.048,.100,.159,65.928,-26.293,-24.339,2.792,18.658,9.822,.153,69.171
 4501.000,174.077,135.292,10.727,-48.765,5.745,7.391,10.438,2.537,.045,.101,.163,74.966,-24.030,-22.535,2.815,17.943,9.593,.156,69.544
 4501.500,168.628,132.294,10.682,-46.952,5.930,7.559,10.477,2.538,.044,.101,.172,76.212,-22.033,-20.726,2.829,17.445,9.493,.160,70.073
 4502.000,169.584,135.351,10.543,-45.172,5.897,7.388,10.532,2.545,.045,.096,.187,76.359,-20.686,-18.948,2.849,17.097,9.298,.166,71.040
 4502.500,176.287,144.355,9.893,-43.498,5.673,6.927,10.604,2.560,.047,.088,.207,86.520,-19.738,-17.278,2.900,17.083,8.859,.178,72.663
 4503.000,184.510,157.230,8.569,-42.037,5.420,6.360,10.618,2.579,.052,.076,.226,95.584,-18.422,-15.819,2.964,14.254,7.538,.192,74.688
 4503.500,189.997,170.311,7.285,-40.899,5.263,5.872,10.669,2.596,.056,.067,.240,104.767,-16.662,-14.684,3.000,10.693,6.091,.205,76.494
 4504.000,192.663,179.891,6.873,-40.162,5.190,5.559,10.729,2.604,.058,.062,.251,110.916,-15.648,-13.950,3.000,10.523,5.880,.211,77.324
 4504.500,192.806,183.543,7.149,-39.834,5.187,5.448,10.764,2.603,.057,.063,.255,111.386,-16.278,-13.625,3.000,11.739,6.358,.206,76.696
 4505.000,190.708,180.624,7.840,-39.840,5.244,5.536,10.793,2.596,.054,.067,.252,104.083,-18.572,-13.634,3.000,13.108,7.071,.193,74.781
 4505.500,186.588,171.555,8.785,-40.042,5.359,5.829,10.830,2.590,.053,.070,.244,92.260,-21.787,-13.839,2.979,15.042,8.141,.175,72.235
 4506.000,180.223,157.706,10.492,-40.275,5.549,6.341,10.857,2.589,.054,.071,.236,86.501,-24.753,-14.075,2.954,18.121,9.860,.157,69.759
 4506.500,172.214,142.471,12.388,-40.398,5.807,7.019,10.909,2.590,.056,.070,.224,85.047,-26.502,-14.201,2.936,19.298,10.835,.144,67.896
 4507.000,165.992,130.096,13.151,-40.321,6.024,7.687,10.935,2.585,.056,.073,.207,79.537,-27.014,-14.127,2.903,19.185,10.720,.138,67.075
 4507.500,163.448,123.651,13.168,-40.023,6.118,8.087,10.977,2.572,.052,.080,.202,71.956,-26.347,-13.832,2.872,19.489,10.522,.142,67.583
 4508.000,166.298,125.131,12.503,-39.540,6.013,7.992,11.045,2.557,.046,.089,.222,69.873,-24.807,-13.352,2.879,18.838,10.016,.155,69.467
 4508.500,175.594,135.426,10.606,-38.950,5.695,7.384,11.101,2.547,.042,.096,.246,79.888,-22.746,-12.765,2.927,14.867,8.326,.177,72.506
 4509.000,189.682,153.532,8.291,-38.345,5.272,6.513,11.140,2.544,.043,.097,.259,93.799,-20.226,-12.163,2.962,11.070,6.539,.203,76.159
 4509.500,206.718,176.517,6.729,-37.808,4.838,5.665,11.206,2.543,.048,.098,.265,101.857,-17.783,-11.628,3.000,9.378,5.600,.227,79.635
 4510.000,226.843,200.832,6.076,-37.391,4.408,4.979,11.244,2.539,.054,.100,.276,109.664,-16.506,-11.214,3.000,8.450,5.049,.246,82.319
 4510.500,248.081,224.178,5.848,-37.114,4.031,4.461,11.295,2.532,.062,.104,.288,117.409,-16.611,-10.941,3.000,7.877,4.803,.259,84.143
 4511.000,269.470,245.481,5.748,-36.971,3.711,4.074,11.436,2.528,.072,.106,.296,113.898,-17.814,-10.801,3.000,7.007,4.825,.268,85.424
 4511.500,288.027,263.539,5.650,-36.940,3.472,3.795,11.640,2.528,.084,.107,.300,105.092,-19.261,-10.773,3.000,6.589,4.652,.275,86.358
 4512.000,301.262,276.196,5.520,-36.992,3.319,3.621,11.649,2.528,.095,.107,.309,96.314,-20.451,-10.827,2.975,6.564,4.256,.276,86.587
 4512.500,304.220,280.997,5.394,-37.096,3.287,3.559,11.675,2.527,.103,.107,.324,99.385,-20.961,-10.934,2.998,6.274,4.188,.269,85.520
 4513.000,297.984,276.393,5.384,-37.225,3.356,3.618,11.607,2.528,.106,.106,.333,95.859,-21.266,-11.066,2.976,7.045,4.518,.251,83.026
 4513.500,286.885,262.729,5.719,-37.359,3.486,3.806,11.716,2.532,.102,.104,.322,81.801,-21.921,-11.203,3.082,8.375,5.143,.228,79.815
 4514.000,274.241,243.611,6.532,-37.485,3.646,4.105,11.588,2.541,.095,.099,.302,71.959,-22.802,-11.332,2.981,11.257,5.987,.209,77.106
 4514.500,262.895,224.838,7.428,-37.590,3.804,4.448,11.410,2.555,.086,.091,.291,70.565,-23.413,-11.440,2.968,12.023,6.381,.200,75.758
 4515.000,253.225,210.724,7.804,-37.662,3.949,4.746,11.401,2.570,.080,.082,.289,75.384,-23.106,-11.515,2.988,11.680,6.594,.200,75.783
 4515.500,243.302,202.490,7.444,-37.695,4.110,4.938,11.427,2.577,.075,.078,.289,83.008,-21.406,-11.551,3.011,11.449,6.565,.205,76.567
 4516.000,235.160,198.969,6.837,-37.697,4.252,5.026,11.474,2.572,.070,.081,.287,86.332,-19.008,-11.556,3.010,10.903,6.248,.213,77.592
 4516.500,229.925,198.205,6.452,-37.683,4.349,5.045,11.542,2.561,.067,.087,.291,85.580,-16.789,-11.544,3.008,10.174,5.948,.220,78.629
 4517.000,228.813,198.942,6.314,-37.672,4.370,5.027,11.674,2.549,.070,.094,.305,82.588,-15.554,-11.536,3.028,8.920,5.717,.226,79.490
 4517.500,232.222,200.687,6.305,-37.673,4.306,4.983,11.578,2.533,.079,.104,.318,85.538,-15.589,-11.541,3.098,8.009,5.642,.230,80.095
 4518.000,237.604,203.263,6.378,-37.687,4.209,4.920,11.537,2.502,.091,.121,.324,93.891,-16.326,-11.557,2.963,8.294,5.629,.233,80.474
 4518.500,243.257,206.564,6.449,-37.708,4.111,4.841,11.592,2.457,.108,.148,.326,95.446,-17.220,-11.581,2.987,7.996,5.424,.235,80.712
 4519.000,248.569,210.404,6.446,-37.738,4.023,4.753,11.665,2.412,.129,.174,.329,99.257,-17.966,-11.614,2.997,7.106,4.951,.235,80.798
 4519.500,253.134,214.706,6.354,-37.787,3.951,4.657,11.596,2.388,.151,.188,.335,97.306,-18.408,-11.666,2.989,6.036,4.486,.234,80.592
 4520.000,257.980,219.819,6.267,-37.875,3.876,4.549,11.547,2.395,.169,.184,.336,90.332,-18.673,-11.757,2.963,6.323,4.566,.230,80.051
 4520.500,263.424,226.428,6.237,-38.025,3.796,4.416,11.396,2.422,.178,.168,.328,89.674,-18.792,-11.910,2.969,6.667,4.731,.227,79.656
 4521.000,267.992,234.556,6.127,-38.255,3.731,4.263,11.457,2.448,.178,.153,.322,101.260,-18.777,-12.143,3.000,6.078,4.517,.231,80.245
 4521.500,268.883,242.209,5.795,-38.570,3.719,4.129,11.605,2.452,.175,.151,.321,103.252,-19.516,-12.462,3.000,5.068,4.070,.238,81.242
 4522.000,262.952,244.614,5.355,-38.960,3.803,4.088,11.353,2.448,.176,.153,.314,92.266,-23.951,-12.854,2.973,4.882,3.792,.232,80.297
 4522.500,246.969,235.321,5.068,-39.396,4.049,4.249,10.983,2.462,.179,.145,.303,89.609,-34.954,-13.293,2.967,9.360,5.684,.201,75.995
 4523.000,222.882,210.819,6.146,-39.844,4.487,4.743,10.566,2.500,.171,.123,.286,85.876,-50.453,-13.745,2.960,35.528,18.640,.153,69.206
 4523.500,199.251,175.173,15.210,-40.279,5.019,5.709,10.489,2.543,.145,.097,.260,75.584,-65.634,-14.182,2.929,76.628,47.201,.103,62.074
 4524.000,177.489,138.394,39.259,-40.682,5.634,7.226,10.459,2.554,.106,.091,.227,61.511,-76.385,-14.588,2.870,81.785,55.749,.068,57.170
 4524.500,160.242,109.915,68.964,-41.043,6.241,9.098,10.451,2.504,.074,.121,.186,46.152,-81.406,-14.952,2.783,48.741,32.987,.061,56.143
 4525.000,148.123,93.554,83.764,-41.359,6.751,10.689,10.545,2.424,.067,.167,.168,41.784,-80.379,-15.271,2.716,35.097,21.133,.079,58.617
 4525.500,132.019,87.657,57.980,-41.628,7.575,11.408,10.808,2.375,.089,.196,.178,48.877,-70.952,-15.542,2.707,26.127,13.920,.110,63.011
 4526.000,113.402,87.547,22.643,-41.850,8.818,11.422,10.820,2.382,.124,.192,.204,62.275,-53.950,-15.768,2.753,10.895,7.390,.142,67.547
 4526.500,100.938,88.449,11.397,-42.034,9.907,11.306,11.000,2.435,.155,.161,.224,65.613,-34.615,-15.954,2.803,8.958,6.178,.161,70.323
 4527.000,98.086,88.485,11.034,-42.189,10.195,11.301,10.984,2.507,.175,.118,.232,61.356,-19.562,-16.113,2.848,8.375,6.275,.160,70.197
 4527.500,102.785,88.833,11.700,-42.331,9.729,11.257,10.626,2.568,.182,.083,.231,57.157,-12.810,-16.258,2.878,9.360,6.993,.149,68.536
 4528.000,112.293,91.102,12.523,-42.471,8.905,10.977,10.466,2.600,.179,.064,.229,57.627,-13.116,-16.400,2.896,11.898,8.285,.141,67.503
 4528.500,120.629,95.457,12.679,-42.611,8.290,10.476,10.371,2.609,.171,.059,.233,62.431,-15.186,-16.544,2.911,13.451,8.906,.140,67.270
 4529.000,123.604,100.759,12.224,-42.744,8.090,9.925,10.361,2.607,.160,.060,.237,62.190,-15.873,-16.679,2.914,13.200,8.519,.138,67.047
 4529.500,121.958,104.900,11.748,-42.852,8.200,9.533,10.395,2.603,.147,.063,.229,64.673,-15.318,-16.790,2.905,10.373,7.528,.134,66.443
 4530.000,117.704,105.458,11.431,-42.912,8.496,9.483,10.243,2.600,.131,.064,.210,66.838,-14.708,-16.853,2.886,9.910,7.278,.127,65.525
 4530.500,111.847,101.195,11.932,-42.907,8.941,9.882,9.798,2.603,.114,.062,.191,67.207,-14.819,-16.851,2.868,12.063,8.024,.119,64.358
 4531.000,105.552,93.258,13.443,-42.832,9.474,10.723,9.621,2.615,.099,.055,.170,67.086,-15.948,-16.779,2.853,14.042,9.543,.109,62.881
 4531.500,99.836,84.418,15.809,-42.699,10.016,11.846,9.588,2.635,.089,.044,.142,55.557,-17.934,-16.649,2.826,20.653,13.468,.097,61.279
 4532.000,94.436,76.418,17.650,-42.542,10.589,13.086,9.459,2.657,.082,.031,.118,46.309,-20.188,-16.495,2.809,27.947,16.964,.087,59.828
 4532.500,89.065,69.003,19.088,-42.400,11.228,14.492,9.337,2.675,.076,.020,.101,46.827,-22.356,-16.356,2.804,29.796,16.760,.079,58.638
 4533.000,82.145,61.790,21.836,-42.303,12.174,16.184,9.267,2.684,.070,.015,.090,45.476,-23.586,-16.262,2.798,25.436,14.918,.073,57.785
 4533.500,73.897,55.276,25.034,-42.265,13.532,18.091,9.189,2.685,.064,.015,.082,43.715,-23.634,-16.227,2.789,24.066,15.101,.069,57.252
 4534.000,64.834,49.742,27.472,-42.275,15.424,20.104,9.112,2.682,.060,.016,.075,41.453,-22.354,-16.240,2.779,32.882,18.634,.066,56.892
 4534.500,58.187,44.905,30.129,-42.312,17.186,22.269,9.056,2.681,.061,.017,.067,42.357,-21.606,-16.279,2.770,38.686,21.108,.064,56.604
 4535.000,53.443,40.600,32.067,-42.348,18.712,24.631,9.000,2.686,.066,.014,.060,44.297,-21.565,-16.319,2.767,36.609,19.530,.063,56.346
 4535.500,49.383,36.954,34.052,-42.369,20.250,27.060,8.942,2.695,.071,.009,.056,46.253,-21.733,-16.343,2.770,33.095,18.245,.060,55.961
 4536.000,45.910,34.015,38.089,-42.371,21.782,29.398,8.921,2.702,.073,.005,.054,44.758,-22.085,-16.347,2.772,30.437,17.726,.056,55.363
 4536.500,42.996,31.703,42.670,-42.359,23.258,31.542,8.882,2.699,.069,.006,.052,41.893,-22.440,-16.338,2.767,31.149,18.036,.051,54.689
 4537.000,40.402,29.992,45.240,-42.344,24.751,33.342,8.825,2.689,.062,.012,.050,38.876,-22.413,-16.326,2.756,35.130,17.810,.047,54.101
 4537.500,38.311,28.802,46.304,-42.335,26.102,34.720,8.782,2.679,.054,.018,.048,39.187,-22.161,-16.321,2.747,39.882,18.885,.044,53.731
 4538.000,36.556,28.005,48.154,-42.338,27.355,35.708,8.755,2.675,.050,.020,.047,42.820,-21.634,-16.327,2.744,47.052,21.656,.043,53.623
 4538.500,35.225,27.493,50.124,-42.352,28.389,36.373,8.761,2.676,.050,.020,.046,41.274,-21.044,-16.343,2.743,50.846,24.352,.043,53.620
 4539.000,34.493,27.165,49.667,-42.369,28.992,36.812,8.748,2.678,.052,.019,.045,37.299,-20.726,-16.364,2.742,52.544,24.910,.043,53.568
 4539.500,33.938,26.971,49.127,-42.381,29.465,37.076,8.745,2.675,.054,.020,.044,35.147,-20.373,-16.378,2.739,46.203,22.031,.042,53.454
 4540.000,33.494,26.917,49.802,-42.372,29.856,37.151,8.753,2.671,.054,.023,.043,37.070,-20.025,-16.372,2.735,38.000,19.699,.041,53.341
 4540.500,33.186,27.022,50.625,-42.324,30.133,37.007,8.757,2.668,.054,.024,.043,34.641,-19.735,-16.327,2.733,37.900,18.723,.041,53.321
 4541.000,32.947,27.290,50.817,-42.223,30.352,36.644,8.756,2.669,.053,.024,.042,32.200,-19.466,-16.229,2.732,40.045,18.567,.041,53.317
 4541.500,32.610,27.601,49.034,-42.064,30.666,36.230,8.761,2.672,.053,.022,.041,36.920,-19.275,-16.073,2.733,40.559,19.505,.040,53.110
 4542.000,32.029,27.607,47.242,-41.852,31.221,36.223,8.743,2.678,.055,.019,.040,38.516,-19.417,-15.863,2.736,44.679,22.646,.037,52.694
 4542.500,31.304,27.002,50.763,-41.596,31.945,37.034,8.723,2.682,.057,.017,.038,35.995,-20.209,-15.610,2.737,55.987,28.455,.034,52.320
 4543.000,30.591,25.954,57.781,-41.311,32.689,38.529,8.717,2.680,.056,.018,.036,30.067,-21.525,-15.328,2.733,58.860,27.554,.033,52.135
 4543.500,29.901,24.933,61.737,-41.011,33.444,40.107,8.710,2.673,.052,.022,.034,34.272,-22.749,-15.032,2.726,53.598,23.119,.032,52.040
 4544.000,29.401,24.187,64.628,-40.711,34.012,41.345,8.716,2.666,.048,.026,.033,40.547,-23.578,-14.734,2.719,52.856,22.086,.031,51.930
 4544.500,29.185,23.762,65.680,-40.422,34.264,42.085,8.719,2.665,.047,.026,.033,38.607,-23.877,-14.449,2.718,47.858,19.713,.031,51.841
 4545.000,29.214,23.747,65.064,-40.154,34.230,42.111,8.728,2.672,.048,.022,.032,38.385,-23.503,-14.184,2.723,42.683,17.791,.031,51.933
 4545.500,29.654,24.182,63.542,-39.911,33.722,41.354,8.747,2.681,.050,.017,.032,41.229,-22.734,-13.943,2.730,44.972,20.771,.034,52.305
 4546.000,30.185,24.926,57.044,-39.693,33.129,40.118,8.755,2.688,.051,.013,.034,40.927,-21.416,-13.729,2.737,43.468,22.358,.037,52.799
 4546.500,30.483,25.694,50.547,-39.500,32.805,38.920,8.763,2.692,.051,.010,.035,42.336,-19.619,-13.538,2.741,40.978,24.151,.040,53.209
 4547.000,30.715,26.278,50.785,-39.327,32.557,38.054,8.757,2.693,.052,.010,.035,44.145,-17.956,-13.368,2.743,37.155,29.431,.042,53.463
 4547.500,30.978,26.822,50.805,-39.162,32.281,37.283,8.756,2.691,.051,.011,.036,40.238,-16.560,-13.206,2.742,31.314,29.083,.043,53.624
 4548.000,31.703,27.706,47.140,-38.992,31.542,36.093,8.782,2.688,.051,.013,.037,38.846,-15.663,-13.039,2.741,31.272,22.605,.045,53.901
 4548.500,33.282,29.216,44.606,-38.803,30.046,34.228,8.816,2.689,.052,.012,.039,38.381,-15.289,-12.853,2.743,28.308,19.514,.049,54.457
 4549.000,35.392,31.436,44.744,-38.593,28.255,31.811,8.845,2.696,.056,.008,.041,39.451,-14.564,-12.646,2.751,23.113,19.455,.055,55.275
 4549.500,37.257,34.337,38.965,-38.384,26.840,29.123,8.882,2.703,.060,.004,.044,43.938,-12.460,-12.440,2.762,23.660,20.077,.062,56.248
 4550.000,39.107,37.671,28.597,-38.214,25.571,26.545,8.917,2.704,.060,.004,.050,47.427,-9.821,-12.273,2.769,24.879,17.510,.069,57.196
 4550.500,40.932,40.794,25.164,-38.132,24.431,24.514,8.917,2.701,.057,.005,.056,47.588,-7.952,-12.194,2.774,25.517,17.206,.073,57.833
 4551.000,42.758,42.993,26.641,-38.179,23.387,23.260,8.933,2.705,.056,.003,.059,46.032,-8.181,-12.244,2.781,27.700,17.869,.074,57.938
 4551.500,44.069,43.882,28.116,-38.368,22.692,22.788,8.939,2.722,.058,-.007,.061,46.019,-10.662,-12.435,2.794,28.150,18.295,.071,57.574
 4552.000,43.626,43.358,29.156,-38.673,22.922,23.064,8.955,2.740,.064,-.018,.060,47.425,-14.487,-12.744,2.808,27.572,19.445,.066,56.892
 4552.500,43.777,41.535,30.116,-39.045,22.843,24.076,8.982,2.748,.068,-.022,.058,46.684,-21.221,-13.118,2.810,26.162,19.211,.058,55.774
 4553.000,46.853,39.352,40.902,-39.419,21.343,25.412,8.995,2.731,.068,-.012,.055,41.848,-30.815,-13.495,2.792,31.426,22.736,.048,54.346
 4553.500,53.387,39.566,71.124,-39.738,18.731,25.274,9.005,2.680,.062,.018,.054,38.053,-40.242,-13.818,2.754,45.633,33.724,.046,54.007
 4554.000,64.437,46.390,81.443,-39.959,15.519,21.556,9.036,2.595,.054,.067,.058,41.744,-46.934,-14.042,2.705,51.033,38.114,.066,56.797
 4554.500,78.207,62.454,48.215,-40.056,12.787,16.012,9.074,2.507,.051,.119,.067,56.578,-47.864,-14.141,2.679,40.730,27.978,.104,62.214
 4555.000,87.035,84.190,17.281,-40.023,11.490,11.878,9.166,2.457,.056,.148,.080,73.631,-40.189,-14.112,2.749,20.473,13.267,.137,66.911
 4555.500,94.401,101.998,9.026,-39.878,10.593,9.804,9.121,2.462,.064,.145,.098,81.613,-29.387,-13.969,2.858,13.895,9.500,.152,69.032
 4556.000,107.914,110.762,14.515,-39.658,9.267,9.028,9.128,2.506,.070,.120,.124,74.411,-23.031,-13.752,2.766,26.721,18.921,.153,69.181
 4556.500,126.721,117.664,17.830,-39.417,7.891,8.499,9.161,2.557,.073,.090,.148,60.115,-21.742,-13.514,2.787,26.478,20.197,.151,68.920
 4557.000,147.302,130.997,11.784,-39.211,6.789,7.634,9.259,2.585,.078,.073,.151,59.307,-21.759,-13.311,2.807,11.734,10.033,.159,69.985
 4557.500,163.609,147.217,7.332,-39.085,6.112,6.793,9.292,2.587,.080,.072,.144,77.187,-20.196,-13.188,2.825,6.200,5.899,.175,72.260
 4558.000,172.275,158.244,7.655,-39.054,5.805,6.319,9.294,2.579,.076,.076,.146,90.796,-17.593,-13.160,2.926,8.889,7.108,.188,74.035
 4558.500,179.094,164.206,9.022,-39.104,5.584,6.090,9.308,2.575,.066,.079,.158,92.622,-16.273,-13.213,2.941,11.493,8.848,.193,74.816
 4559.000,190.832,171.212,8.601,-39.197,5.240,5.841,9.334,2.577,.056,.078,.172,95.757,-16.904,-13.309,2.965,9.624,8.156,.198,75.572
 4559.500,205.726,181.671,7.606,-39.290,4.861,5.504,9.387,2.579,.052,.076,.184,103.794,-17.955,-13.404,3.000,7.710,7.299,.203,76.263
 4560.000,218.353,193.112,7.026,-39.356,4.580,5.178,9.421,2.580,.055,.076,.204,100.170,-18.214,-13.474,3.000,6.607,7.055,.204,76.383
 4560.500,230.762,203.498,6.722,-39.394,4.333,4.914,9.472,2.580,.063,.076,.227,97.531,-18.512,-13.514,2.980,6.970,6.672,.205,76.469
 4561.000,244.340,213.236,6.610,-39.417,4.093,4.690,9.625,2.580,.073,.076,.242,103.722,-19.353,-13.541,3.000,7.752,6.720,.209,77.015
 4561.500,258.276,223.054,6.541,-39.444,3.872,4.483,9.745,2.574,.077,.080,.252,100.963,-20.526,-13.570,3.000,7.623,6.653,.216,78.105
 4562.000,271.003,232.882,6.427,-39.486,3.690,4.294,9.826,2.556,.076,.090,.261,102.666,-21.601,-13.615,3.000,6.388,6.044,.227,79.654
 4562.500,283.753,242.631,6.298,-39.553,3.524,4.122,9.990,2.534,.076,.103,.269,104.172,-22.621,-13.685,3.000,5.244,5.386,.234,80.654
 4563.000,296.793,252.501,6.168,-39.665,3.369,3.960,10.030,2.521,.088,.110,.276,100.706,-23.569,-13.800,3.000,5.309,5.088,.231,80.164
 4563.500,308.295,262.451,6.011,-39.856,3.244,3.810,10.093,2.521,.108,.111,.286,99.167,-24.219,-13.994,2.997,5.368,4.970,.224,79.226
 4564.000,318.303,272.011,5.873,-40.180,3.142,3.676,10.194,2.515,.120,.114,.301,105.906,-24.618,-14.321,3.000,5.229,4.895,.225,79.398
 4564.500,325.669,280.727,5.817,-40.698,3.071,3.562,9.985,2.476,.114,.137,.313,111.305,-24.700,-14.842,3.000,5.452,4.862,.241,81.588
 4565.000,328.710,287.552,5.685,-41.476,3.042,3.478,10.383,2.395,.096,.184,.320,108.037,-24.538,-15.623,3.000,4.778,4.498,.267,85.221
 4565.500,323.916,289.291,5.308,-42.559,3.087,3.457,10.774,2.310,.085,.234,.316,92.610,-24.329,-16.709,2.968,3.734,4.074,.285,87.803
 4566.000,313.063,281.253,5.215,-43.948,3.194,3.556,10.594,2.267,.088,.259,.299,90.155,-24.934,-18.101,2.957,3.655,3.984,.285,87.761
 4566.500,298.889,261.978,6.148,-45.575,3.346,3.817,9.657,2.276,.093,.254,.277,92.899,-26.773,-19.731,2.963,5.551,4.872,.267,85.272
 4567.000,280.751,236.332,7.474,-47.295,3.562,4.231,9.481,2.318,.086,.229,.257,92.654,-29.174,-21.454,2.950,8.015,6.334,.239,81.293
 4567.500,257.774,210.376,8.392,-48.927,3.879,4.753,9.469,2.372,.069,.198,.239,85.680,-31.367,-23.088,2.905,9.314,7.316,.213,77.695
 4568.000,231.721,185.149,9.191,-50.311,4.315,5.401,9.431,2.423,.054,.168,.222,83.916,-33.239,-24.476,2.888,10.839,8.369,.196,75.236
 4568.500,202.269,159.118,10.876,-51.358,4.944,6.285,9.423,2.470,.050,.141,.200,85.283,-34.269,-25.526,2.885,13.631,10.308,.180,72.984
 4569.000,173.933,133.171,14.164,-52.065,5.749,7.509,9.426,2.511,.053,.116,.178,84.867,-34.466,-26.235,2.882,16.885,12.571,.163,70.590
 4569.500,148.455,110.379,16.730,-52.485,6.736,9.060,9.427,2.537,.057,.101,.162,84.276,-33.465,-26.659,2.878,18.610,13.671,.151,68.840
 4570.000,128.690,92.483,18.268,-52.694,7.771,10.813,9.423,2.538,.055,.101,.151,83.542,-31.769,-26.870,2.872,19.845,14.296,.147,68.328
 4570.500,111.993,79.016,19.661,-52.753,8.929,12.656,9.426,2.520,.050,.111,.149,81.688,-28.856,-26.932,2.859,21.247,15.117,.150,68.656
 4571.000,99.015,69.445,20.248,-52.699,10.099,14.400,9.425,2.503,.044,.121,.160,78.599,-25.323,-26.881,2.822,21.955,15.544,.153,69.132
 4571.500,91.748,63.662,20.054,-52.546,10.899,15.708,9.426,2.497,.042,.124,.176,77.306,-22.604,-26.731,2.820,20.855,15.115,.155,69.464
 4572.000,87.644,61.229,19.288,-52.284,11.410,16.332,9.431,2.503,.044,.121,.180,79.124,-20.295,-26.472,2.835,19.645,14.470,.156,69.575
 4572.500,85.598,61.311,18.939,-51.893,11.683,16.310,9.424,2.511,.048,.116,.172,80.821,-18.241,-26.084,2.851,20.820,14.669,.155,69.490
 4573.000,84.780,63.059,18.547,-51.351,11.795,15.858,9.415,2.517,.051,.113,.168,80.385,-16.195,-25.545,2.845,20.478,14.369,.154,69.343
 4573.500,85.008,65.920,16.982,-50.643,11.764,15.170,9.422,2.522,.053,.110,.170,74.276,-14.170,-24.840,2.814,18.406,13.189,.154,69.242
 4574.000,87.128,69.770,15.447,-49.777,11.477,14.333,9.417,2.526,.054,.107,.172,73.219,-12.752,-23.977,2.816,17.270,12.359,.153,69.188
 4574.500,90.798,74.958,14.678,-48.782,11.014,13.341,9.412,2.534,.053,.103,.172,77.356,-11.963,-22.985,2.831,16.283,11.892,.154,69.273
 4575.000,96.613,82.204,14.072,-47.713,10.351,12.165,9.412,2.544,.051,.097,.171,78.497,-11.965,-21.919,2.837,15.777,11.711,.158,69.926
 4575.500,104.884,92.133,13.665,-46.643,9.534,10.854,9.397,2.550,.045,.093,.173,86.984,-12.439,-20.852,2.898,15.580,11.335,.171,71.627
 4576.000,113.139,104.348,12.722,-45.656,8.839,9.583,9.394,2.551,.038,.093,.186,96.265,-12.090,-19.868,2.969,13.419,9.798,.188,74.077
 4576.500,122.341,116.708,10.386,-44.844,8.174,8.568,9.398,2.551,.033,.093,.211,97.642,-11.507,-19.058,2.981,10.186,7.795,.200,75.816
 4577.000,131.092,126.426,8.714,-44.289,7.628,7.910,9.394,2.556,.033,.090,.228,96.618,-11.134,-18.506,2.972,9.451,7.371,.199,75.667
 4577.500,139.519,132.360,8.980,-44.049,7.168,7.555,9.389,2.561,.036,.087,.233,96.625,-12.014,-18.270,2.972,10.247,7.630,.187,73.985
 4578.000,149.079,135.646,9.423,-44.143,6.708,7.372,9.346,2.543,.039,.097,.232,101.604,-14.676,-18.366,3.000,10.507,7.687,.169,71.447
 4578.500,160.326,138.646,9.963,-44.540,6.237,7.213,9.324,2.470,.039,.140,.233,94.276,-18.283,-18.767,2.954,11.381,8.329,.151,68.908
 4579.000,172.661,144.628,11.162,-45.170,5.792,6.914,9.575,2.343,.043,.215,.243,86.847,-21.261,-19.399,2.913,11.693,8.678,.151,68.848
 4579.500,187.723,158.093,11.192,-45.931,5.327,6.325,10.670,2.217,.062,.289,.261,91.294,-22.796,-20.164,2.946,9.317,7.379,.181,73.076
 4580.000,206.644,181.774,9.164,-46.722,4.839,5.501,11.438,2.136,.098,.336,.285,100.237,-22.587,-20.957,2.996,5.372,5.216,.227,79.634
 4580.500,224.790,211.500,6.689,-47.455,4.449,4.728,11.801,2.102,.138,.355,.307,101.568,-20.259,-21.694,2.993,3.386,3.905,.273,86.126
 4581.000,242.507,238.998,5.466,-48.078,4.124,4.184,11.976,2.096,.168,.359,.335,99.411,-17.433,-22.319,2.991,2.980,3.393,.308,91.127
 4581.500,258.421,259.514,5.153,-48.572,3.870,3.853,11.908,2.103,.183,.355,.371,99.595,-15.894,-22.816,2.989,3.043,3.234,.325,93.424
 4582.000,272.696,272.431,5.127,-48.949,3.667,3.671,11.408,2.119,.187,.345,.387,101.290,-18.243,-23.197,2.987,3.141,3.302,.326,93.656
 4582.500,282.794,277.969,5.120,-49.237,3.536,3.598,11.064,2.141,.182,.333,.363,99.806,-28.293,-23.487,2.986,3.242,3.393,.312,91.582
 4583.000,281.206,273.625,4.990,-49.464,3.556,3.655,10.530,2.166,.170,.318,.315,93.998,-47.202,-23.717,2.974,3.473,3.494,.267,85.347
 4583.500,264.244,253.251,5.479,-49.654,3.784,3.949,9.322,2.205,.154,.295,.271,79.665,-68.881,-23.909,2.881,6.359,5.433,.200,75.760
 4584.000,237.135,214.754,16.433,-49.820,4.217,4.656,8.806,2.272,.133,.256,.220,63.087,-86.564,-24.079,2.720,25.843,18.109,.126,65.334
 4584.500,207.123,167.183,66.504,-49.969,4.828,5.982,8.759,2.366,.108,.201,.145,50.844,-97.564,-24.230,2.677,59.043,40.904,.065,56.704
 4585.000,176.335,123.899,109.210,-50.096,5.671,8.071,8.729,2.468,.082,.142,.105,44.376,-101.410,-24.361,2.684,73.814,52.751,.034,52.282
 4585.500,145.451,91.592,98.824,-50.193,6.875,10.918,8.692,2.547,.062,.095,.084,43.708,-98.911,-24.461,2.705,67.087,48.387,.029,51.552
 4586.000,114.715,68.276,85.323,-50.252,8.717,14.646,8.630,2.592,.048,.069,.072,37.953,-91.446,-24.523,2.715,56.418,39.088,.033,52.195
 4586.500,82.029,49.927,85.984,-50.277,12.191,20.029,8.605,2.607,.042,.060,.066,29.783,-78.886,-24.551,2.717,61.873,42.174,.039,53.010
 4587.000,57.453,35.762,95.545,-50.286,17.406,27.962,8.579,2.606,.038,.061,.065,28.060,-65.493,-24.562,2.715,69.313,47.510,.044,53.770
 4587.500,43.719,26.552,101.239,-50.306,22.873,37.661,8.549,2.595,.036,.067,.068,34.148,-56.093,-24.585,2.711,66.264,44.499,.048,54.251
 4588.000,37.005,21.766,85.273,-50.361,27.023,45.943,8.480,2.581,.034,.076,.071,38.490,-52.664,-24.643,2.708,54.535,37.609,.048,54.301
 4588.500,34.612,19.556,76.907,-50.466,28.892,51.135,8.462,2.573,.033,.080,.072,33.907,-55.370,-24.751,2.703,60.714,46.353,.046,54.010
 4589.000,34.444,18.438,144.885,-50.621,29.032,54.235,8.444,2.579,.036,.076,.070,27.990,-61.020,-24.910,2.704,74.637,59.527,.043,53.522
 4589.500,33.996,17.975,219.834,-50.814,29.415,55.632,8.438,2.602,.044,.063,.066,29.255,-64.226,-25.105,2.713,76.437,62.117,.039,53.014
 4590.000,32.492,18.012,180.816,-51.024,30.777,55.519,8.446,2.637,.055,.043,.061,31.951,-62.673,-25.318,2.731,73.514,57.479,.036,52.664
 4590.500,30.687,18.131,122.979,-51.229,32.587,55.154,8.445,2.671,.065,.023,.056,33.807,-57.577,-25.527,2.749,73.663,53.931,.036,52.529
 4591.000,29.079,18.009,119.186,-51.417,34.389,55.528,8.442,2.693,.069,.010,.052,35.625,-51.000,-25.717,2.760,77.756,54.677,.036,52.571
 4591.500,28.022,17.820,115.977,-51.586,35.687,56.116,8.440,2.698,.068,.007,.048,34.058,-44.704,-25.889,2.760,75.830,52.054,.037,52.774
 4592.000,27.574,18.006,99.643,-51.751,36.266,55.536,8.435,2.694,.063,.009,.047,34.240,-39.261,-26.057,2.756,71.251,47.563,.040,53.096
 4592.500,27.411,18.723,81.713,-51.950,36.482,53.411,8.422,2.688,.058,.013,.047,43.763,-34.544,-26.259,2.753,65.836,43.101,.042,53.400
 4593.000,27.058,19.660,69.645,-52.230,36.957,50.864,8.418,2.683,.055,.016,.046,48.221,-30.936,-26.541,2.748,68.735,44.697,.042,53.494
 4593.500,26.587,20.329,67.512,-52.633,37.612,49.191,8.425,2.679,.054,.018,.044,45.960,-30.029,-26.947,2.743,67.284,43.921,.040,53.225
 4594.000,26.033,20.389,71.928,-53.181,38.413,49.045,8.430,2.676,.053,.020,.041,41.865,-32.452,-27.499,2.737,72.877,49.596,.036,52.615
 4594.500,25.395,19.758,97.007,-53.875,39.379,50.612,8.428,2.672,.052,.022,.038,36.140,-37.188,-28.196,2.730,87.786,62.472,.030,51.815
 4595.000,24.669,18.544,119.430,-54.697,40.537,53.926,8.431,2.667,.049,.025,.036,30.367,-42.654,-29.021,2.724,89.357,66.034,.025,51.089
 4595.500,23.560,16.967,141.189,-55.620,42.446,58.938,8.430,2.661,.048,.028,.036,29.783,-47.321,-29.947,2.719,87.729,70.333,.023,50.767
 4596.000,22.113,15.384,157.035,-56.610,45.222,65.003,8.426,2.658,.049,.030,.038,29.993,-50.674,-30.940,2.719,82.449,74.087,.025,50.994
 4596.500,20.283,14.204,195.692,-57.619,49.302,70.401,8.428,2.659,.053,.030,.042,31.102,-52.054,-31.951,2.725,75.404,78.569,.029,51.586
 4597.000,18.314,13.522,229.012,-58.576,54.604,73.956,8.426,2.660,.057,.029,.048,29.348,-51.273,-32.911,2.732,55.085,64.651,.033,52.194
 4597.500,16.426,13.094,225.621,-59.393,60.880,76.370,8.426,2.657,.057,.031,.051,29.353,-48.451,-33.732,2.733,37.464,43.832,.036,52.542
 4598.000,14.729,12.748,215.520,-59.981,67.893,78.444,8.420,2.650,.054,.035,.051,29.418,-44.006,-34.322,2.728,40.459,39.288,.035,52.458
 4598.500,13.323,12.454,208.262,-60.268,75.060,80.297,8.431,2.648,.050,.036,.047,29.548,-38.759,-34.612,2.723,55.952,46.851,.031,51.928
 4599.000,11.971,12.227,191.650,-60.224,83.537,81.783,8.423,2.654,.048,.033,.043,27.598,-32.747,-34.571,2.722,70.573,57.809,.026,51.141
 4599.500,10.903,12.051,172.770,-59.867,91.718,82.978,8.423,2.664,.046,.027,.038,25.266,-27.456,-34.217,2.723,75.484,68.957,.020,50.325
 4600.000,10.512,11.748,170.369,-59.252,95.131,85.121,8.423,2.669,.043,.024,.034,25.097,-25.123,-33.605,2.722,78.599,77.122,.015,49.677
 4600.500,10.733,11.267,177.687,-58.442,93.175,88.757,8.440,2.665,.038,.026,.032,25.972,-25.798,-32.798,2.717,78.351,74.831,.013,49.310
 4601.000,11.601,10.820,185.885,-57.482,86.197,92.422,8.454,2.658,.033,.030,.030,24.853,-28.895,-31.841,2.710,75.276,71.924,.012,49.152
 4601.500,12.844,10.507,190.670,-56.386,77.860,95.175,8.437,2.653,.032,.033,.029,25.444,-32.211,-30.748,2.706,72.421,72.699,.011,49.081
 4602.000,14.299,10.333,187.873,-55.147,69.934,96.775,8.452,2.648,.033,.036,.028,28.332,-34.145,-29.511,2.702,71.994,75.517,.011,49.114
 4602.500,16.983,10.572,163.289,-53.756,58.884,94.590,8.452,2.641,.035,.040,.028,32.683,-36.329,-28.123,2.699,71.568,74.043,.013,49.364
 4603.000,21.052,11.866,128.258,-52.223,47.502,84.275,8.479,2.635,.037,.044,.029,35.543,-37.518,-26.593,2.697,68.830,67.289,.017,49.906
 4603.500,26.206,15.143,90.537,-50.585,38.159,66.036,8.534,2.636,.038,.043,.032,40.155,-36.086,-24.959,2.702,58.880,56.037,.025,51.007
 4604.000,34.391,21.518,60.504,-48.909,29.078,46.472,8.554,2.642,.040,.040,.037,44.852,-34.109,-23.286,2.711,46.035,41.009,.039,52.965
 4604.500,45.470,31.909,35.685,-47.285,21.992,31.339,8.580,2.640,.042,.041,.044,51.385,-30.476,-21.665,2.721,34.035,29.102,.056,55.479
 4605.000,56.682,46.279,19.114,-45.813,17.642,21.608,8.619,2.617,.043,.054,.056,67.605,-24.107,-20.195,2.730,18.284,15.495,.076,58.299
 4605.500,70.040,63.622,17.693,-44.576,14.278,15.718,8.622,2.573,.046,.080,.076,79.037,-19.342,-18.961,2.825,15.042,11.771,.102,61.873
 4606.000,83.854,83.186,18.746,-43.623,11.925,12.021,8.704,2.524,.051,.109,.093,79.736,-17.845,-18.012,2.835,17.306,12.719,.129,65.737
 4606.500,92.469,102.459,13.257,-42.964,10.814,9.760,8.759,2.497,.060,.124,.096,87.627,-20.770,-17.355,2.902,12.618,9.084,.146,68.138
 4607.000,94.660,113.990,9.423,-42.576,10.564,8.773,8.766,2.505,.069,.120,.095,92.927,-31.587,-16.970,2.943,8.835,6.871,.145,68.006
 4607.500,91.628,111.352,14.445,-42.423,10.914,8.981,8.803,2.545,.074,.097,.098,83.029,-48.142,-16.820,2.868,13.683,10.624,.124,65.039
 4608.000,85.356,96.970,37.112,-42.459,11.716,10.312,8.814,2.598,.077,.066,.090,64.829,-63.807,-16.859,2.752,26.322,21.950,.089,60.034
 4608.500,80.130,78.979,94.618,-42.619,12.480,12.662,8.821,2.641,.076,.040,.073,48.571,-75.680,-17.022,2.752,53.621,47.836,.056,55.448
 4609.000,74.583,63.110,149.649,-42.817,13.408,15.845,8.861,2.662,.072,.028,.060,43.719,-81.567,-17.223,2.749,67.120,63.962,.039,53.014
 4609.500,64.113,50.057,151.781,-42.953,15.597,19.977,8.914,2.664,.069,.027,.053,42.055,-78.721,-17.361,2.742,67.041,62.797,.037,52.735
 4610.000,52.128,38.901,120.628,-42.932,19.184,25.706,8.939,2.662,.069,.028,.050,35.080,-68.852,-17.343,2.736,63.199,58.754,.047,54.085
 4610.500,42.269,30.151,95.544,-42.689,23.658,33.166,9.061,2.665,.072,.026,.049,37.969,-55.162,-17.104,2.738,49.618,48.772,.059,55.913
 4611.000,38.867,25.348,76.374,-42.202,25.729,39.450,9.109,2.670,.075,.023,.048,47.555,-43.775,-16.620,2.741,44.590,41.867,.064,56.602
 4611.500,44.061,26.426,57.472,-41.488,22.696,37.842,9.120,2.671,.072,.023,.048,45.955,-38.675,-15.908,2.743,44.084,34.577,.063,56.459
 4612.000,58.298,35.506,41.034,-40.594,17.153,28.164,9.204,2.666,.064,.026,.052,43.893,-37.968,-15.017,2.742,35.431,25.328,.070,57.394
 4612.500,78.365,53.912,27.654,-39.587,12.761,18.549,9.276,2.656,.058,.031,.059,49.978,-36.261,-14.013,2.745,25.428,18.935,.090,60.224
 4613.000,101.162,80.728,16.851,-38.545,9.885,12.387,9.354,2.646,.054,.037,.071,63.039,-31.623,-12.974,2.757,15.587,12.484,.120,64.449
 4613.500,122.066,111.946,10.336,-37.548,8.192,8.933,9.454,2.635,.054,.044,.090,72.917,-24.019,-11.980,2.784,9.745,8.026,.152,69.007
 4614.000,142.724,141.722,7.413,-36.670,7.006,7.056,9.512,2.618,.053,.054,.117,80.996,-16.935,-11.105,2.854,7.672,6.087,.178,72.719
 4614.500,161.815,165.686,6.763,-35.970,6.180,6.036,9.559,2.596,.049,.066,.150,90.226,-12.775,-10.408,2.922,7.277,5.633,.193,74.876
 4615.000,180.359,182.543,7.095,-35.479,5.544,5.478,9.624,2.576,.045,.078,.185,98.853,-12.806,-9.920,2.991,7.401,5.744,.198,75.543
 4615.500,196.088,192.840,7.396,-35.192,5.100,5.186,9.690,2.563,.042,.086,.204,105.210,-15.323,-9.637,3.000,7.415,5.759,.196,75.279
 4616.000,207.411,197.272,7.523,-35.080,4.821,5.069,9.758,2.559,.041,.088,.199,123.863,-18.427,-9.527,3.000,7.730,5.936,.192,74.677
 4616.500,213.785,196.711,8.043,-35.098,4.678,5.084,9.808,2.562,.040,.086,.185,131.656,-21.120,-9.548,3.000,9.092,6.598,.187,73.917
 4617.000,214.255,193.000,8.395,-35.204,4.667,5.181,9.894,2.569,.041,.082,.180,109.312,-22.875,-9.657,3.000,10.594,6.935,.181,73.063
 4617.500,212.412,188.408,8.609,-35.364,4.708,5.308,9.954,2.576,.042,.079,.185,103.707,-24.171,-9.820,3.000,13.369,8.325,.177,72.616
 4618.000,211.369,184.870,9.419,-35.553,4.731,5.409,10.038,2.579,.046,.077,.194,123.860,-25.432,-10.012,3.000,16.065,10.111,.178,72.686
 4618.500,211.078,183.385,9.241,-35.747,4.738,5.453,10.114,2.579,.052,.077,.196,141.631,-26.425,-10.209,3.000,11.817,7.967,.179,72.778
 4619.000,215.214,184.282,9.629,-35.925,4.647,5.426,10.196,2.576,.058,.078,.188,154.564,-27.366,-10.390,3.000,10.809,7.256,.181,73.161
 4619.500,226.033,189.183,10.727,-36.069,4.424,5.286,10.239,2.572,.064,.081,.186,170.867,-27.956,-10.537,3.000,14.573,9.282,.190,74.412
 4620.000,238.882,200.500,9.183,-36.174,4.186,4.988,10.286,2.565,.071,.085,.197,174.559,-26.898,-10.645,3.000,13.143,8.500,.204,76.412
 4620.500,250.954,217.143,6.564,-36.245,3.985,4.605,10.354,2.557,.074,.090,.213,152.461,-24.201,-10.719,3.000,6.625,5.527,.221,78.839
 4621.000,262.939,233.678,5.482,-36.297,3.803,4.279,10.427,2.546,.072,.096,.230,131.585,-21.452,-10.773,3.000,5.260,4.803,.236,80.929
 4621.500,273.635,245.959,5.526,-36.344,3.655,4.066,10.464,2.533,.063,.104,.250,126.482,-19.988,-10.823,3.000,6.136,5.199,.242,81.706
 4622.000,285.043,254.777,5.841,-36.394,3.508,3.925,10.510,2.525,.054,.108,.269,118.106,-20.400,-10.876,3.000,6.621,5.512,.240,81.445
 4622.500,299.586,262.966,6.057,-36.447,3.338,3.803,10.529,2.528,.049,.106,.284,103.976,-22.132,-10.932,3.000,6.776,5.634,.238,81.201
 4623.000,314.614,271.440,6.036,-36.498,3.178,3.684,10.548,2.540,.050,.099,.297,98.972,-23.863,-10.987,2.996,6.635,5.504,.240,81.432
 4623.500,325.217,279.329,5.847,-36.545,3.075,3.580,10.584,2.551,.053,.093,.302,95.703,-24.618,-11.036,2.914,6.355,5.300,.244,82.045
 4624.000,330.180,285.991,5.625,-36.591,3.029,3.497,10.573,2.554,.056,.091,.299,92.788,-24.419,-11.085,3.065,6.060,5.085,.250,82.835
 4624.500,331.511,290.959,5.424,-36.646,3.016,3.437,10.592,2.550,.059,.094,.298,93.330,-23.900,-11.143,3.052,5.748,4.845,.255,83.526
 4625.000,329.353,293.065,5.309,-36.720,3.036,3.412,10.639,2.546,.064,.096,.300,95.339,-23.481,-11.220,2.852,5.345,4.611,.256,83.710
 4625.500,325.597,290.719,5.382,-36.817,3.071,3.440,10.647,2.547,.072,.095,.299,90.682,-23.603,-11.320,3.036,4.649,4.449,.251,83.080
 4626.000,322.549,283.509,5.683,-36.929,3.100,3.527,10.649,2.555,.078,.091,.290,84.358,-24.435,-11.435,3.000,4.921,4.691,.242,81.790
 4626.500,319.134,273.440,6.102,-37.036,3.134,3.657,10.649,2.563,.079,.086,.283,80.469,-25.448,-11.545,2.988,6.471,5.372,.232,80.296
 4627.000,314.450,263.682,6.422,-37.110,3.180,3.792,10.644,2.569,.074,.083,.284,77.586,-26.060,-11.622,2.984,7.141,5.740,.224,79.135
 4627.500,311.841,256.170,6.496,-37.131,3.207,3.904,10.649,2.570,.067,.082,.282,79.196,-26.389,-11.645,2.987,7.034,5.748,.221,78.748
 4628.000,308.740,251.148,6.417,-37.099,3.239,3.982,10.647,2.570,.065,.082,.275,81.601,-26.093,-11.616,2.982,6.565,5.600,.223,79.080
 4628.500,303.921,248.204,6.270,-37.040,3.290,4.029,10.647,2.570,.068,.082,.268,86.531,-25.197,-11.560,2.979,6.044,5.359,.227,79.680
 4629.000,299.339,246.945,6.140,-36.994,3.341,4.049,10.654,2.567,.069,.084,.268,85.327,-24.206,-11.518,2.975,6.249,5.369,.231,80.132
 4629.500,297.015,247.277,6.093,-37.003,3.367,4.044,10.649,2.562,.068,.087,.275,87.620,-23.583,-11.530,2.984,6.590,5.469,.231,80.222
 4630.000,297.517,249.234,6.094,-37.095,3.361,4.012,10.594,2.559,.064,.088,.288,88.261,-23.471,-11.625,3.006,6.632,5.457,.230,80.082
 4630.500,300.201,252.434,6.124,-37.289,3.331,3.961,10.577,2.562,.062,.087,.301,91.350,-23.709,-11.822,3.069,6.343,5.390,.230,80.071
 4631.000,303.104,256.262,6.162,-37.603,3.299,3.902,10.559,2.564,.061,.085,.309,93.976,-23.887,-12.138,2.839,6.389,5.409,.232,80.343
 4631.500,304.810,260.518,6.128,-38.056,3.281,3.839,10.514,2.563,.061,.086,.320,85.305,-23.717,-12.594,3.144,6.669,5.413,.235,80.802
 4632.000,302.746,264.474,5.971,-38.671,3.303,3.781,10.468,2.560,.061,.088,.330,80.346,-22.980,-13.212,3.149,6.521,5.261,.238,81.174
 4632.500,294.854,265.282,5.715,-39.466,3.391,3.770,10.455,2.563,.065,.086,.324,85.594,-21.877,-14.011,3.240,6.220,5.077,.236,80.905
 4633.000,281.067,258.778,5.520,-40.446,3.558,3.864,10.419,2.576,.070,.078,.298,84.180,-21.157,-14.993,3.035,6.313,5.106,.227,79.632
 4633.500,265.259,242.973,5.758,-41.579,3.770,4.116,10.368,2.590,.074,.070,.267,80.679,-21.925,-16.129,2.982,7.868,5.798,.214,77.828
 4634.000,251.938,220.525,6.762,-42.793,3.969,4.535,10.301,2.584,.073,.073,.244,76.895,-24.564,-17.346,2.939,10.452,7.182,.209,77.119
 4634.500,243.964,197.758,8.400,-43.975,4.099,5.057,10.253,2.539,.067,.100,.238,74.475,-28.233,-18.531,2.898,12.201,8.417,.224,79.188
 4635.000,241.523,182.633,10.575,-45.005,4.140,5.476,10.293,2.457,.067,.148,.253,65.482,-31.284,-19.564,2.848,12.652,8.584,.252,83.195
 4635.500,243.979,181.388,11.897,-45.791,4.099,5.513,10.877,2.375,.086,.196,.279,61.432,-32.291,-20.353,2.824,8.651,6.701,.282,87.415
 4636.000,246.878,193.841,9.978,-46.290,4.051,5.159,11.590,2.322,.120,.227,.303,60.604,-30.091,-20.855,2.819,4.222,4.661,.315,92.124
 4636.500,249.470,213.000,6.816,-46.514,4.009,4.695,11.844,2.297,.150,.242,.319,62.471,-25.282,-21.081,2.827,3.334,3.788,.343,96.034
 4637.000,255.838,231.057,5.344,-46.519,3.909,4.328,11.756,2.285,.166,.249,.325,72.621,-20.291,-21.089,2.852,3.455,3.634,.346,96.441
 4637.500,269.959,245.894,5.101,-46.390,3.704,4.067,11.520,2.281,.171,.251,.320,76.823,-17.674,-20.964,2.876,3.291,3.540,.330,94.193
 4638.000,292.490,261.348,5.267,-46.223,3.419,3.826,11.006,2.286,.176,.248,.320,73.380,-18.173,-20.799,2.851,3.192,3.427,.318,92.436
 4638.500,321.539,281.172,5.459,-46.100,3.110,3.556,10.716,2.297,.184,.242,.325,79.010,-20.852,-20.680,2.902,3.157,3.335,.324,93.369
 4639.000,345.625,304.081,5.286,-46.077,2.893,3.289,10.566,2.295,.186,.242,.329,93.324,-24.308,-20.660,2.971,3.081,3.235,.350,97.015
 4639.500,355.221,323.262,4.813,-46.170,2.815,3.093,10.533,2.269,.177,.258,.328,91.804,-30.173,-20.755,2.965,3.147,3.248,.378,101.036
 4640.000,345.642,328.587,4.495,-46.357,2.893,3.043,10.549,2.233,.158,.279,.320,78.346,-41.932,-20.945,2.883,4.874,4.275,.382,101.587
 4640.500,317.572,311.059,5.582,-46.591,3.149,3.215,10.217,2.228,.136,.282,.297,62.811,-59.103,-21.182,2.766,17.638,11.260,.343,96.084
 4641.000,281.389,269.056,12.002,-46.811,3.554,3.717,9.357,2.281,.115,.251,.248,43.049,-77.285,-21.405,2.716,37.984,23.773,.262,84.629
 4641.500,247.634,212.832,27.811,-46.958,4.038,4.699,9.150,2.388,.095,.188,.162,26.568,-93.042,-21.555,2.687,45.551,34.386,.160,70.116
 4642.000,213.914,158.978,59.928,-46.986,4.675,6.290,9.079,2.514,.080,.114,.110,24.083,-103.673,-21.586,2.707,51.492,44.580,.076,58.304
 4642.500,181.031,116.779,108.710,-46.871,5.524,8.563,8.991,2.607,.071,.060,.087,28.504,-108.290,-21.474,2.739,54.842,45.667,.037,52.725
 4643.000,144.310,85.058,130.464,-46.612,6.930,11.757,8.910,2.649,.065,.035,.075,32.289,-105.217,-21.217,2.754,56.967,46.995,.029,51.638
 4643.500,108.196,60.735,129.541,-46.219,9.243,16.465,8.857,2.667,.062,.025,.068,36.701,-94.578,-20.828,2.759,52.935,42.890,.033,52.168
 4644.000,80.011,43.626,110.010,-45.716,12.498,22.922,8.779,2.679,.063,.018,.064,39.656,-78.628,-20.328,2.764,41.019,31.989,.040,53.220
 4644.500,62.396,34.487,70.794,-45.138,16.027,28.996,8.746,2.688,.065,.013,.063,39.410,-60.767,-19.753,2.770,29.414,21.448,.050,54.550
 4645.000,54.315,32.003,41.920,-44.529,18.411,31.247,8.717,2.689,.067,.012,.064,42.192,-44.960,-19.146,2.773,25.389,17.180,.057,55.636
 4645.500,51.733,33.168,31.413,-43.939,19.330,30.149,8.652,2.682,.064,.016,.062,48.327,-33.860,-18.560,2.768,26.053,17.215,.059,55.828
 4646.000,51.577,35.145,28.105,-43.416,19.388,28.453,8.613,2.672,.059,.022,.057,46.091,-30.154,-18.039,2.754,28.971,18.603,.053,54.994
 4646.500,51.403,36.010,34.572,-42.990,19.454,27.770,8.564,2.667,.053,.025,.050,38.518,-33.722,-17.617,2.740,32.935,21.263,.043,53.534
 4647.000,49.793,35.028,50.939,-42.676,20.083,28.549,8.515,2.670,.050,.023,.043,35.994,-40.839,-17.305,2.734,34.962,24.777,.032,51.972
 4647.500,46.489,32.472,67.780,-42.469,21.510,30.796,8.459,2.678,.049,.019,.037,32.952,-47.839,-17.101,2.733,41.026,31.140,.022,50.680
 4648.000,41.518,28.864,89.810,-42.356,24.086,34.645,8.451,2.687,.050,.014,.032,30.351,-52.631,-16.991,2.732,46.378,35.033,.016,49.761
 4648.500,35.261,24.686,113.510,-42.320,28.360,40.508,8.440,2.691,.051,.011,.028,31.258,-54.352,-16.958,2.731,50.247,37.381,.011,49.120
 4649.000,30.127,20.526,135.336,-42.347,33.193,48.719,8.425,2.691,.051,.011,.025,31.967,-55.015,-16.988,2.728,55.501,42.112,.008,48.662
 4649.500,27.466,16.917,162.470,-42.428,36.408,59.113,8.419,2.690,.050,.011,.023,34.045,-56.852,-17.072,2.725,60.370,47.007,.006,48.374
 4650.000,25.260,14.139,183.638,-42.555,39.589,70.724,8.395,2.690,.049,.012,.022,35.055,-57.678,-17.203,2.723,59.428,44.928,.005,48.248
 4650.500,22.758,12.214,191.893,-42.724,43.941,81.875,8.372,2.690,.048,.012,.021,32.604,-56.521,-17.374,2.722,59.933,44.028,.005,48.238
 4651.000,20.611,11.002,198.485,-42.923,48.517,90.890,8.371,2.694,.047,.010,.020,33.827,-54.707,-17.576,2.724,58.295,43.765,.006,48.286
 4651.500,19.103,10.329,204.927,-43.133,52.347,96.815,8.370,2.700,.046,.006,.019,37.135,-53.232,-17.789,2.727,60.185,46.166,.006,48.311
 4652.000,17.846,10.049,212.566,-43.337,56.036,99.515,8.369,2.707,.046,.002,.018,39.200,-51.602,-17.996,2.731,71.236,54.753,.006,48.289
 4652.500,16.815,10.051,222.835,-43.522,59.471,99.496,8.371,2.714,.047,-.002,.018,40.224,-49.756,-18.183,2.736,77.104,59.405,.005,48.268
 4653.000,16.097,10.185,219.450,-43.686,62.124,98.184,8.368,2.718,.048,-.005,.018,39.343,-47.902,-18.350,2.739,72.215,53.015,.006,48.278
 4653.500,15.434,10.312,206.791,-43.839,64.794,96.979,8.367,2.718,.050,-.005,.018,36.318,-45.601,-18.507,2.740,69.056,50.736,.006,48.343
 4654.000,14.816,10.417,198.427,-43.993,67.493,96.001,8.365,2.714,.051,-.002,.019,33.346,-43.085,-18.663,2.737,65.440,48.847,.007,48.420
 4654.500,14.367,10.540,200.125,-44.144,69.605,94.880,8.368,2.707,.052,.002,.019,32.844,-40.800,-18.817,2.733,66.919,51.663,.007,48.446
 4655.000,14.027,10.658,200.246,-44.275,71.293,93.822,8.369,2.701,.054,.005,.019,35.435,-38.492,-18.952,2.728,63.370,46.422,.007,48.451
 4655.500,13.821,10.763,184.563,-44.365,72.352,92.915,8.365,2.697,.055,.008,.018,33.946,-36.137,-19.044,2.724,57.376,37.883,.007,48.504
 4656.000,13.731,10.908,169.959,-44.398,72.829,91.675,8.364,2.695,.055,.009,.018,31.821,-33.880,-19.080,2.722,57.857,36.106,.008,48.581
 4656.500,13.659,11.096,156.031,-44.381,73.213,90.126,8.372,2.697,.054,.008,.018,32.885,-31.905,-19.066,2.724,55.609,35.488,.008,48.595
 4657.000,13.557,11.207,154.742,-44.337,73.765,89.230,8.372,2.702,.054,.005,.018,33.318,-30.472,-19.025,2.728,56.944,38.909,.007,48.554
 4657.500,13.527,11.139,159.209,-44.296,73.928,89.773,8.370,2.708,.056,.001,.018,35.596,-29.972,-18.988,2.732,58.683,40.115,.007,48.538
 4658.000,13.551,10.966,157.230,-44.281,73.798,91.189,8.369,2.710,.057,.000,.018,35.490,-30.243,-18.975,2.733,57.072,37.751,.008,48.571
 4658.500,13.547,10.827,155.164,-44.292,73.819,92.365,8.413,2.706,.056,.003,.017,38.652,-30.883,-18.989,2.729,54.677,37.251,.008,48.586
 4659.000,13.607,10.756,169.031,-44.314,73.493,92.970,8.418,2.696,.053,.008,.017,44.541,-31.884,-19.014,2.723,57.172,38.634,.007,48.520
 4659.500,13.733,10.774,177.218,-44.323,72.815,92.817,8.430,2.686,.049,.014,.018,46.407,-32.850,-19.026,2.718,54.808,36.907,.006,48.396
 4660.000,13.830,10.883,174.146,-44.301,72.304,91.885,8.442,2.679,.046,.018,.018,47.248,-33.209,-19.007,2.714,53.905,36.868,.006,48.311
 4660.500,13.798,10.956,169.796,-44.239,72.472,91.271,8.443,2.680,.046,.017,.017,47.590,-32.757,-18.947,2.714,58.696,37.112,.006,48.322
 4661.000,13.550,10.855,158.556,-44.137,73.802,92.125,8.440,2.687,.047,.014,.017,47.826,-31.701,-18.849,2.718,61.783,37.872,.006,48.373
 4661.500,13.067,10.637,157.981,-44.002,76.530,94.014,8.443,2.693,.048,.010,.017,45.134,-30.517,-18.716,2.720,62.224,36.422,.006,48.398
 4662.000,12.413,10.455,164.052,-43.836,80.563,95.645,8.449,2.694,.048,.009,.017,41.084,-29.552,-18.553,2.720,60.440,34.334,.006,48.389
 4662.500,11.708,10.348,176.777,-43.642,85.412,96.633,8.451,2.694,.047,.009,.018,39.527,-28.728,-18.363,2.721,62.826,37.195,.006,48.366
 4663.000,11.146,10.276,198.680,-43.422,89.720,97.310,8.454,2.694,.047,.009,.019,44.983,-27.887,-18.145,2.723,60.561,37.069,.006,48.352
 4663.500,10.707,10.250,202.402,-43.175,93.396,97.558,8.457,2.692,.047,.010,.020,52.950,-26.359,-17.902,2.726,62.113,38.982,.006,48.378
 4664.000,10.196,10.295,180.377,-42.905,98.078,97.137,8.461,2.689,.047,.012,.020,54.950,-23.375,-17.635,2.725,63.368,40.944,.007,48.443
 4664.500,9.745,10.361,160.599,-42.616,102.615,96.516,8.458,2.686,.047,.014,.021,53.704,-19.920,-17.348,2.724,64.756,42.557,.007,48.528
 4665.000,9.553,10.369,159.842,-42.310,104.678,96.439,8.461,2.685,.048,.014,.021,48.719,-17.431,-17.045,2.722,68.706,45.159,.008,48.632
 4665.500,9.828,10.290,161.211,-41.991,101.747,97.187,8.517,2.687,.048,.014,.022,45.249,-16.986,-16.729,2.722,73.514,48.090,.009,48.767
 4666.000,10.471,10.125,153.520,-41.661,95.502,98.769,8.540,2.688,.048,.013,.022,50.181,-17.853,-16.402,2.725,68.108,42.970,.010,48.936
 4666.500,11.254,9.907,143.540,-41.317,88.859,100.936,8.534,2.686,.048,.014,.023,59.911,-18.730,-16.061,2.727,62.151,38.691,.011,49.117
 4667.000,12.964,9.905,136.621,-40.948,77.140,100.956,8.542,2.679,.047,.018,.025,64.570,-21.694,-15.695,2.727,61.896,37.338,.013,49.390
 4667.500,16.725,10.968,130.989,-40.537,59.792,91.175,8.551,2.667,.043,.025,.028,65.239,-27.932,-15.287,2.725,62.858,37.129,.018,50.088
 4668.000,23.429,14.610,118.490,-40.068,42.683,68.448,8.572,2.651,.037,.035,.032,68.389,-35.361,-14.820,2.726,60.799,35.318,.031,51.896
 4668.500,32.941,22.665,93.853,-39.540,30.357,44.120,8.620,2.630,.033,.047,.039,76.802,-39.917,-14.296,2.793,56.062,32.054,.058,55.683
 4669.000,44.451,36.079,53.783,-38.990,22.497,27.717,8.621,2.604,.031,.062,.053,120.015,-39.172,-13.749,3.000,41.864,24.297,.100,61.623
 4669.500,55.925,52.970,23.772,-38.483,17.881,18.879,8.623,2.573,.033,.080,.079,246.920,-32.258,-13.245,3.000,21.807,12.753,.147,68.265
 4670.000,65.804,69.221,12.195,-38.105,15.197,14.446,8.630,2.544,.036,.097,.117,379.738,-21.378,-12.869,3.000,12.912,8.015,.181,73.114
 4670.500,76.257,82.146,11.979,-37.919,13.114,12.174,8.633,2.523,.040,.109,.152,375.822,-12.652,-12.687,3.000,16.382,10.088,.193,74.802
 4671.000,88.673,92.617,13.943,-37.949,11.277,10.797,8.647,2.510,.047,.117,.178,255.857,-9.803,-12.719,3.000,19.528,12.194,.191,74.540
 4671.500,100.834,103.344,14.658,-38.166,9.917,9.676,8.708,2.502,.060,.122,.187,150.275,-10.263,-12.940,3.000,19.043,12.130,.191,74.523
 4672.000,108.293,114.071,12.436,-38.518,9.234,8.766,8.766,2.504,.081,.121,.169,108.412,-9.769,-13.294,3.000,12.710,8.660,.194,75.009
 4672.500,109.943,119.658,8.362,-38.956,9.096,8.357,8.724,2.521,.100,.110,.146,93.530,-7.890,-13.736,2.948,8.575,6.501,.194,75.007
 4673.000,109.273,116.676,8.892,-39.456,9.151,8.571,8.718,2.549,.105,.094,.140,90.768,-7.190,-14.238,2.926,11.679,8.416,.184,73.545
 4673.500,107.868,108.959,11.565,-40.004,9.271,9.178,8.717,2.570,.093,.082,.139,81.436,-8.449,-14.789,2.857,13.685,9.938,.161,70.215
 4674.000,107.796,102.851,13.163,-40.577,9.277,9.723,8.722,2.577,.072,.078,.129,78.946,-11.009,-15.366,2.823,14.724,10.629,.136,66.749
 4674.500,110.107,100.299,13.937,-41.126,9.082,9.970,8.730,2.574,.054,.079,.117,79.371,-13.811,-15.917,2.830,15.037,10.965,.123,64.935
 4675.000,110.069,99.249,13.626,-41.578,9.085,10.076,8.730,2.576,.046,.079,.111,75.977,-14.674,-16.372,2.786,14.661,10.992,.119,64.402
 4675.500,107.252,97.969,13.204,-41.854,9.324,10.207,8.728,2.586,.046,.073,.109,73.545,-13.675,-16.651,2.779,15.445,11.101,.119,64.348
 4676.000,105.627,96.665,13.219,-41.892,9.467,10.345,8.724,2.596,.049,.066,.112,75.268,-12.683,-16.692,2.794,16.102,10.928,.121,64.574
 4676.500,107.231,96.436,12.735,-41.660,9.326,10.370,8.724,2.598,.051,.066,.118,80.504,-12.824,-16.462,2.847,15.487,10.579,.124,65.046
 4677.000,114.541,98.853,12.477,-41.156,8.731,10.116,8.725,2.585,.051,.073,.124,80.188,-14.970,-15.962,2.842,15.180,10.495,.129,65.807
 4677.500,128.686,106.549,12.993,-40.417,7.771,9.385,8.731,2.558,.050,.089,.132,77.842,-18.717,-15.226,2.807,15.023,10.527,.139,67.203
 4678.000,149.505,122.711,13.499,-39.512,6.689,8.149,8.731,2.517,.052,.113,.150,79.360,-22.617,-14.324,2.830,13.996,9.803,.159,70.015
 4678.500,174.010,148.044,12.371,-38.524,5.747,6.755,8.742,2.470,.063,.141,.183,85.621,-24.778,-13.339,2.887,10.947,7.740,.191,74.523
 4679.000,194.401,177.558,8.874,-37.538,5.144,5.632,8.837,2.437,.081,.160,.213,96.288,-23.795,-12.356,2.970,6.338,5.110,.224,79.143
 4679.500,208.126,202.201,6.169,-36.630,4.805,4.946,8.858,2.434,.099,.161,.224,99.869,-21.302,-11.450,2.999,3.537,3.827,.243,81.843
 4680.000,219.681,215.443,5.977,-35.868,4.552,4.642,8.581,2.459,.106,.147,.232,101.305,-20.778,-10.692,3.000,4.226,4.317,.244,82.045
 4680.500,231.417,218.570,7.474,-35.328,4.321,4.575,8.557,2.495,.098,.126,.238,103.217,-23.489,-10.154,3.000,6.589,5.566,.230,79.984
 4681.000,244.591,218.418,8.827,-35.085,4.089,4.578,8.543,2.525,.081,.108,.240,96.691,-28.091,-9.915,2.973,7.907,6.236,.208,76.956
 4681.500,257.222,219.870,9.535,-35.201,3.888,4.548,8.539,2.537,.065,.101,.239,94.431,-32.372,-10.034,2.955,8.355,6.484,.196,75.261
 4682.000,263.256,223.040,9.903,-35.698,3.799,4.484,8.536,2.533,.056,.104,.235,98.038,-35.173,-10.533,2.984,8.921,6.774,.203,76.268
 4682.500,258.291,226.039,9.542,-36.549,3.872,4.424,8.534,2.521,.054,.111,.228,97.911,-38.539,-11.387,2.983,8.804,6.575,.221,78.768
 4683.000,240.527,225.016,7.809,-37.683,4.157,4.444,8.498,2.516,.058,.113,.209,94.953,-47.010,-12.524,2.959,7.027,5.449,.226,79.492
 4683.500,215.302,212.502,6.434,-39.002,4.645,4.706,8.487,2.527,.064,.107,.184,85.200,-61.421,-13.846,2.884,12.859,7.875,.205,76.500
 4684.000,188.295,183.312,15.368,-40.402,5.311,5.455,8.480,2.550,.068,.094,.163,59.360,-76.104,-15.249,2.798,44.240,22.255,.161,70.215
 4684.500,162.829,143.686,58.091,-41.792,6.141,6.960,8.475,2.573,.067,.080,.132,37.774,-86.257,-16.642,2.766,73.100,36.297,.108,62.718
 4685.000,143.184,107.463,108.390,-43.120,6.984,9.306,8.477,2.592,.061,.069,.100,33.388,-91.333,-17.973,2.744,67.944,33.731,.069,57.234
 4685.500,125.796,81.557,98.128,-44.374,7.949,12.261,8.479,2.608,.055,.060,.077,36.010,-91.438,-19.230,2.730,50.578,26.253,.052,54.919
 4686.000,102.516,62.719,70.930,-45.575,9.755,15.944,8.482,2.627,.051,.049,.064,38.546,-85.932,-20.434,2.729,44.797,25.276,.047,54.196
 4686.500,77.184,47.024,83.426,-46.757,12.956,21.266,8.484,2.648,.051,.036,.058,39.171,-77.331,-21.619,2.737,51.977,29.294,.044,53.664
 4687.000,56.590,34.294,101.148,-47.941,17.671,29.159,8.483,2.667,.054,.025,.055,43.104,-69.302,-22.806,2.747,53.430,28.700,.039,53.074
 4687.500,42.470,25.193,100.345,-49.122,23.546,39.693,8.477,2.678,.058,.019,.053,44.928,-63.626,-23.990,2.753,61.550,32.708,.035,52.506
 4688.000,34.887,19.463,135.424,-50.266,28.664,51.379,8.477,2.681,.060,.017,.053,43.383,-61.510,-25.136,2.755,82.226,46.517,.031,51.957
 4688.500,32.112,16.316,187.446,-51.320,31.141,61.288,8.474,2.680,.060,.017,.053,45.171,-62.166,-26.193,2.754,89.942,53.797,.028,51.522
 4689.000,31.618,15.014,191.381,-52.228,31.628,66.605,8.477,2.675,.057,.020,.052,47.724,-62.701,-27.105,2.750,86.318,54.813,.027,51.343
 4689.500,30.991,14.919,161.759,-52.947,32.267,67.027,8.479,2.665,.052,.026,.052,45.710,-60.478,-27.826,2.742,86.422,56.113,.028,51.402
 4690.000,29.265,15.308,117.890,-53.446,34.170,65.325,8.483,2.652,.047,.034,.052,46.657,-55.672,-28.328,2.734,81.029,51.373,.029,51.555
 4690.500,27.092,15.556,105.424,-53.708,36.912,64.284,8.488,2.642,.045,.040,.052,51.863,-50.691,-28.593,2.730,74.116,48.655,.029,51.645
 4691.000,25.548,15.490,146.884,-53.728,39.142,64.558,8.486,2.635,.043,.044,.051,54.218,-47.232,-28.616,2.727,75.982,53.287,.029,51.578
 4691.500,24.800,15.472,159.148,-53.516,40.322,64.635,8.479,2.634,.041,.044,.050,53.258,-44.225,-28.407,2.724,72.739,52.129,.028,51.419
 4692.000,24.500,15.923,117.418,-53.100,40.815,62.801,8.479,2.639,.040,.041,.048,55.971,-39.971,-27.995,2.725,53.766,39.383,.027,51.344
 4692.500,24.455,16.846,82.051,-52.523,40.892,59.363,8.474,2.651,.041,.035,.046,61.518,-34.430,-27.420,2.732,35.698,28.658,.028,51.463
 4693.000,24.706,18.010,76.896,-51.822,40.476,55.524,8.478,2.666,.044,.026,.046,67.153,-29.073,-26.722,2.743,33.930,29.460,.030,51.701
 4693.500,25.285,19.273,73.023,-51.018,39.549,51.887,8.483,2.679,.046,.018,.046,64.427,-25.237,-25.921,2.751,32.252,28.079,.031,51.940
 4694.000,26.035,20.505,64.506,-50.105,38.410,48.768,8.521,2.684,.046,.015,.046,59.362,-23.095,-25.011,2.752,29.843,23.450,.033,52.215
 4694.500,26.857,21.578,66.332,-49.060,37.235,46.343,8.537,2.680,.043,.018,.046,56.040,-22.674,-23.969,2.747,30.532,22.767,.036,52.526
 4695.000,27.571,22.403,58.831,-47.869,36.270,44.637,8.527,2.668,.041,.024,.045,62.951,-24.478,-22.781,2.742,29.735,21.528,.037,52.691
 4695.500,27.948,22.844,51.965,-46.543,35.780,43.776,8.531,2.658,.039,.030,.045,77.206,-28.699,-21.458,2.798,31.813,22.211,.036,52.564
 4696.000,28.106,22.774,74.548,-45.120,35.579,43.910,8.537,2.652,.038,.034,.045,84.426,-33.885,-20.038,2.879,42.976,31.171,.034,52.323
 4696.500,28.788,22.525,134.487,-43.659,34.737,44.395,8.541,2.649,.038,.036,.046,71.454,-37.856,-18.580,2.747,51.890,39.556,.034,52.376
 4697.000,31.222,23.225,130.382,-42.219,32.028,43.058,8.542,2.646,.038,.037,.045,64.344,-39.676,-17.143,2.730,43.549,31.934,.038,52.919
 4697.500,35.928,26.143,65.580,-40.849,27.833,38.251,8.556,2.641,.037,.040,.045,66.880,-38.840,-15.776,2.731,30.205,21.215,.045,53.897
 4698.000,43.155,31.792,35.844,-39.587,23.172,31.455,8.566,2.636,.037,.044,.048,56.966,-35.940,-14.516,2.723,28.756,19.968,.055,55.348
 4698.500,52.755,40.572,41.371,-38.466,18.955,24.648,8.594,2.633,.038,.045,.053,44.266,-32.262,-13.399,2.722,34.746,23.461,.069,57.269
 4699.000,62.381,52.926,34.099,-37.529,16.031,18.894,8.635,2.637,.043,.042,.062,49.981,-27.770,-12.464,2.736,28.911,18.736,.083,59.226
 4699.500,69.443,66.408,16.414,-36.827,14.400,15.058,8.622,2.646,.049,.037,.069,60.043,-22.770,-11.765,2.754,17.463,11.246,.093,60.599
 4700.000,74.336,75.443,12.879,-36.410,13.452,13.255,8.625,2.652,.051,.034,.072,63.041,-19.833,-11.352,2.762,22.850,12.950,.095,61.013
 4700.500,79.452,77.382,21.601,-36.310,12.586,12.923,8.630,2.650,.047,.035,.072,56.756,-21.062,-11.254,2.757,35.822,18.406,.092,60.475
 4701.000,86.649,76.019,26.750,-36.527,11.541,13.155,8.634,2.640,.042,.041,.070,48.800,-24.896,-11.474,2.747,33.616,18.143,.086,59.717
 4701.500,96.594,77.117,24.287,-37.045,10.353,12.967,8.658,2.628,.040,.048,.069,49.903,-28.275,-11.995,2.737,34.700,19.724,.088,59.994
 4702.000,106.877,83.326,22.037,-37.856,9.357,12.001,8.678,2.616,.042,.055,.071,51.821,-28.528,-12.809,2.734,41.044,22.974,.101,61.852
 4702.500,113.459,93.985,16.420,-38.971,8.814,10.640,8.715,2.602,.047,.063,.078,57.103,-24.441,-13.927,2.737,28.754,15.930,.122,64.695
 4703.000,117.018,106.658,10.418,-40.403,8.546,9.376,8.716,2.584,.051,.074,.089,66.902,-17.893,-15.362,2.744,13.631,9.106,.142,67.580
 4703.500,119.559,118.322,8.888,-42.128,8.364,8.451,8.717,2.563,.052,.086,.107,71.946,-12.038,-17.090,2.763,10.406,7.915,.157,69.679
 4704.000,121.370,126.461,8.972,-44.058,8.239,7.908,8.725,2.546,.049,.096,.124,75.225,-9.248,-19.023,2.782,10.329,7.889,.163,70.524
 4704.500,122.811,129.631,9.543,-46.039,8.143,7.714,8.725,2.534,.045,.103,.130,75.454,-10.158,-21.007,2.784,11.224,8.377,.161,70.331
 4705.000,124.610,127.520,10.779,-47.876,8.025,7.842,8.726,2.530,.043,.105,.122,71.489,-13.819,-22.847,2.762,14.465,9.760,.156,69.630
 4705.500,124.475,120.913,12.465,-49.377,8.034,8.270,8.730,2.532,.044,.104,.111,67.091,-17.945,-24.350,2.742,18.471,11.559,.150,68.781
 4706.000,120.090,111.574,14.162,-50.376,8.327,8.963,8.740,2.536,.047,.102,.104,64.530,-20.470,-25.352,2.735,21.281,13.126,.145,67.984
 4706.500,114.293,101.756,16.802,-50.752,8.749,9.827,8.741,2.541,.050,.099,.105,62.621,-21.191,-25.731,2.737,24.686,14.890,.140,67.349
 4707.000,109.644,93.891,17.661,-50.436,9.120,10.651,8.735,2.547,.052,.096,.114,63.684,-20.294,-25.418,2.749,25.387,15.184,.137,66.935
 4707.500,107.949,90.172,15.481,-49.409,9.264,11.090,8.730,2.552,.054,.092,.124,66.246,-18.354,-24.395,2.765,22.738,13.631,.137,66.854
 4708.000,112.544,91.941,13.655,-47.716,8.885,10.877,8.731,2.555,.053,.090,.130,68.400,-16.935,-22.704,2.775,19.376,11.875,.139,67.232
 4708.500,125.960,100.229,12.434,-45.467,7.939,9.977,8.733,2.555,.053,.091,.133,70.430,-17.064,-20.458,2.782,15.076,10.041,.147,68.254
 4709.000,147.096,116.796,10.824,-42.851,6.798,8.562,8.736,2.550,.055,.093,.141,75.047,-17.960,-17.845,2.799,11.650,8.387,.161,70.232
 4709.500,173.023,143.692,9.176,-40.116,5.780,6.959,8.782,2.541,.061,.099,.161,80.004,-18.437,-15.113,2.839,9.020,6.767,.182,73.219
 4710.000,205.749,179.888,7.414,-37.534,4.860,5.559,9.016,2.530,.072,.105,.195,91.769,-18.995,-12.534,2.934,6.566,5.267,.206,76.659
 4710.500,241.387,219.463,6.015,-35.346,4.143,4.557,9.508,2.525,.089,.108,.224,102.711,-19.427,-10.486,3.000,5.081,4.484,.228,79.758
 4711.000,274.406,256.143,5.377,-33.714,3.644,3.904,9.846,2.528,.108,.107,.240,99.754,-19.956,-8.994,2.998,4.622,4.232,.244,82.031
 4711.500,309.511,287.130,5.313,-32.688,3.231,3.483,10.035,2.533,.123,.103,.260,101.020,-21.996,-8.108,3.000,4.633,4.151,.253,83.289
 4712.000,346.335,311.424,5.454,-32.224,2.887,3.211,9.963,2.532,.133,.104,.286,103.650,-25.216,-7.784,3.000,4.476,4.240,.256,83.768
 4712.500,379.018,328.437,5.530,-32.222,2.638,3.045,9.861,2.514,.137,.114,.307,98.148,-28.277,-7.922,2.994,4.328,4.191,.260,84.270
 4713.000,406.359,339.559,5.490,-32.569,2.461,2.945,10.154,2.477,.139,.137,.313,90.497,-30.621,-8.409,3.119,3.970,3.921,.268,85.433
 4713.500,424.882,348.239,5.350,-33.170,2.354,2.872,10.497,2.419,.140,.170,.317,85.459,-31.960,-9.150,2.954,3.500,3.739,.281,87.311
 4714.000,430.399,355.462,5.151,-33.958,2.323,2.813,10.668,2.349,.145,.211,.327,86.077,-32.554,-10.078,2.940,3.140,3.509,.297,89.542
 4714.500,422.060,358.163,4.922,-34.900,2.369,2.792,10.555,2.286,.154,.248,.331,86.706,-33.358,-11.160,2.941,2.919,3.302,.305,90.631
 4715.000,401.082,351.212,5.013,-35.993,2.493,2.847,9.988,2.257,.167,.265,.319,85.198,-35.140,-12.393,2.934,2.851,3.287,.291,88.700
 4715.500,376.627,328.864,6.481,-37.274,2.655,3.041,8.953,2.281,.181,.251,.300,75.060,-38.232,-13.814,2.848,3.618,3.821,.256,83.739
 4716.000,352.735,292.367,8.551,-38.828,2.835,3.420,8.796,2.357,.190,.206,.284,66.959,-41.599,-15.508,2.827,4.536,4.772,.212,77.501
 4716.500,326.714,253.860,9.783,-40.784,3.061,3.939,8.595,2.456,.189,.149,.272,66.004,-43.583,-17.604,2.871,4.855,5.703,.177,72.547
 4717.000,297.231,223.308,11.249,-43.303,3.364,4.478,8.633,2.535,.177,.103,.259,68.381,-43.327,-20.263,2.904,5.436,5.803,.162,70.371
 4717.500,265.024,199.152,11.305,-46.562,3.773,5.021,8.612,2.561,.154,.087,.241,71.073,-41.194,-23.662,2.906,5.176,5.647,.161,70.254
 4718.000,228.510,175.937,10.834,-50.715,4.376,5.684,8.292,2.539,.126,.100,.230,72.736,-38.675,-27.955,2.885,7.300,6.776,.163,70.572
 4718.500,190.473,151.832,10.337,-55.844,5.250,6.586,8.190,2.498,.103,.124,.234,66.803,-39.136,-33.224,2.851,8.340,6.717,.158,69.821
 4719.000,158.403,126.573,9.337,-61.904,6.313,7.901,8.008,2.466,.089,.143,.236,60.326,-45.143,-39.424,2.827,6.789,6.520,.146,68.229
 4719.500,133.371,100.540,17.689,-68.689,7.498,9.946,7.940,2.450,.082,.152,.229,51.429,-54.024,-46.349,2.801,7.509,8.314,.139,67.174
 4720.000,114.633,77.150,44.402,-75.854,8.724,12.962,7.899,2.445,.076,.155,.224,45.067,-61.972,-53.654,2.786,6.803,9.053,.139,67.159
 4720.500,99.565,59.760,68.361,-82.985,10.044,16.734,7.872,2.441,.071,.157,.223,43.366,-66.733,-60.925,2.782,6.390,9.012,.146,68.097
 4721.000,85.705,47.903,70.819,-89.709,11.668,20.876,7.865,2.430,.066,.163,.223,44.627,-67.775,-67.789,2.776,6.263,8.918,.156,69.532
 4721.500,70.265,39.219,71.580,-95.779,14.232,25.498,7.848,2.414,.061,.173,.225,42.309,-64.784,-73.999,2.767,6.241,9.001,.165,70.783
 4722.000,56.192,32.168,80.350,-101.108,17.796,31.086,7.820,2.394,.058,.185,.228,39.109,-59.932,-79.468,2.756,6.271,9.157,.170,71.512
 4722.500,46.035,26.581,89.995,-105.740,21.723,37.620,7.818,2.371,.058,.198,.228,39.274,-55.675,-84.240,2.743,6.272,9.131,.172,71.833
 4723.000,39.310,22.647,100.118,-109.798,25.439,44.155,7.826,2.346,.057,.213,.230,40.300,-52.523,-88.438,2.731,6.216,9.049,.172,71.825
 4723.500,35.407,20.059,111.204,-113.415,28.243,49.852,7.818,2.322,.057,.227,.240,37.653,-50.546,-92.195,2.725,6.118,9.011,.168,71.311
 4724.000,33.887,18.387,110.626,-116.689,29.510,54.387,7.807,2.309,.057,.234,.250,36.540,-49.843,-95.609,2.725,6.065,9.007,.161,70.288
 4724.500,32.620,17.455,107.969,-119.676,30.656,57.289,7.808,2.313,.058,.232,.246,36.800,-48.488,-98.736,2.724,6.057,9.005,.154,69.290
 4725.000,30.958,17.077,103.563,-122.395,32.302,58.557,7.832,2.333,.060,.220,.232,42.154,-46.251,-101.595,2.721,5.874,8.807,.152,68.953
 4725.500,29.004,16.949,96.887,-124.852,34.478,59.000,7.830,2.357,.060,.206,.223,44.588,-43.686,-104.192,2.725,5.764,8.638,.156,69.579
 4726.000,27.142,16.982,107.932,-127.061,36.844,58.886,7.815,2.367,.057,.201,.228,41.437,-41.231,-106.541,2.737,5.870,8.687,.167,71.114
 4726.500,26.109,17.351,117.299,-129.042,38.301,57.633,7.816,2.360,.054,.205,.236,37.905,-39.459,-108.662,2.741,5.852,8.727,.180,72.912
 4727.000,25.596,18.046,105.676,-130.829,39.068,55.413,7.830,2.349,.054,.211,.238,41.712,-37.536,-110.589,2.736,5.837,8.712,.188,74.050
 4727.500,25.184,18.677,95.783,-132.461,39.708,53.540,7.823,2.346,.056,.213,.236,48.124,-34.956,-112.361,2.733,5.818,8.692,.188,74.061
 4728.000,24.570,18.904,89.035,-133.979,40.699,52.897,7.825,2.354,.059,.208,.235,46.686,-32.015,-114.019,2.737,5.762,8.616,.180,73.025
 4728.500,23.522,18.654,81.947,-135.420,42.513,53.606,7.824,2.370,.062,.199,.234,45.221,-29.457,-115.600,2.745,5.701,8.514,.168,71.261
 4729.000,22.271,17.990,77.836,-136.801,44.902,55.585,7.826,2.390,.066,.187,.233,48.823,-28.462,-117.121,2.756,5.704,8.492,.153,69.179
 4729.500,21.453,17.123,92.032,-138.121,46.613,58.400,7.821,2.406,.070,.178,.224,54.103,-29.819,-118.581,2.757,5.802,8.594,.141,67.411
 4730.000,20.883,16.375,120.135,-139.353,47.885,61.070,7.833,2.409,.071,.176,.203,57.717,-31.767,-119.953,2.737,5.911,8.715,.135,66.655
 4730.500,20.406,15.969,133.968,-140.457,49.005,62.622,7.833,2.397,.068,.183,.187,59.733,-32.603,-121.197,2.713,5.860,8.634,.139,67.154
 4731.000,19.945,15.830,116.541,-141.390,50.137,63.171,7.832,2.375,.062,.196,.189,60.638,-31.869,-122.270,2.703,5.798,8.530,.148,68.463
 4731.500,19.366,15.639,100.660,-142.118,51.636,63.944,7.833,2.355,.058,.208,.205,57.021,-30.171,-123.138,2.707,5.832,8.587,.157,69.682
 4732.000,18.806,15.204,101.260,-142.627,53.174,65.771,7.827,2.345,.058,.214,.216,53.462,-29.036,-123.787,2.711,5.889,8.723,.160,70.130
 4732.500,18.537,14.698,112.316,-142.925,53.946,68.034,7.821,2.348,.061,.211,.215,60.392,-29.600,-124.225,2.712,5.947,8.908,.157,69.743
 4733.000,18.764,14.394,122.543,-143.034,53.294,69.471,7.824,2.364,.067,.202,.209,67.815,-31.900,-124.474,2.716,6.004,9.104,.151,68.884
 4733.500,19.477,14.405,128.034,-142.987,51.342,69.418,7.833,2.387,.072,.189,.206,76.140,-35.102,-124.567,2.727,6.140,9.294,.145,68.029
 4734.000,20.458,14.746,137.410,-142.819,48.882,67.816,7.828,2.409,.072,.176,.204,80.087,-38.097,-124.539,2.738,6.291,9.474,.141,67.478
 4734.500,21.716,15.398,137.336,-142.557,46.049,64.944,7.826,2.426,.071,.166,.201,73.154,-40.581,-124.417,2.744,6.236,9.573,.139,67.227
 4735.000,23.222,16.318,128.733,-142.216,43.062,61.284,7.810,2.434,.068,.161,.191,62.591,-42.492,-124.216,2.739,6.190,9.783,.139,67.103
 4735.500,24.935,17.482,123.595,-141.800,40.105,57.201,7.816,2.433,.065,.162,.179,59.068,-43.985,-123.940,2.726,6.498,10.016,.137,66.932
 4736.000,27.149,18.895,118.138,-141.309,36.833,52.924,7.830,2.428,.063,.165,.173,64.020,-45.809,-123.589,2.717,6.930,10.037,.135,66.635
 4736.500,29.562,20.500,114.083,-140.747,33.828,48.780,7.815,2.423,.062,.168,.168,58.215,-47.756,-123.167,2.710,7.226,10.141,.132,66.248
 4737.000,31.968,22.208,105.842,-140.122,31.281,45.028,7.822,2.421,.061,.169,.158,51.085,-49.793,-122.682,2.700,7.779,10.875,.130,65.961
 4737.500,34.460,23.947,106.842,-139.434,29.019,41.759,7.803,2.422,.060,.168,.147,49.103,-52.001,-122.134,2.691,8.266,11.628,.131,65.967
 4738.000,36.678,25.594,116.211,-138.670,27.264,39.072,7.823,2.424,.060,.167,.139,50.766,-53.489,-121.510,2.685,7.880,11.348,.133,66.249
 4738.500,38.585,27.024,112.581,-137.809,25.917,37.004,7.815,2.429,.062,.165,.134,56.276,-53.630,-120.789,2.683,7.234,10.710,.135,66.588
 4739.000,40.252,28.197,94.669,-136.826,24.844,35.465,7.801,2.437,.065,.160,.135,57.045,-52.268,-119.946,2.688,6.666,10.124,.136,66.748
 4739.500,41.339,29.088,80.899,-135.708,24.191,34.379,7.821,2.448,.069,.153,.141,58.673,-49.409,-118.968,2.699,6.185,9.613,.135,66.656
 4740.000,41.990,29.646,77.164,-134.454,23.815,33.731,7.866,2.457,.074,.148,.150,68.064,-45.886,-117.854,2.712,5.883,9.164,.134,66.452
 4740.500,42.394,29.860,67.433,-133.074,23.588,33.489,7.869,2.459,.078,.147,.156,66.433,-42.768,-116.614,2.719,5.652,8.675,.133,66.324
 4741.000,42.446,29.779,54.942,-131.580,23.559,33.581,7.864,2.453,.078,.150,.159,61.097,-41.127,-115.260,2.718,5.654,8.518,.133,66.276
 4741.500,42.215,29.504,57.629,-129.980,23.688,33.894,7.883,2.445,.076,.155,.157,63.773,-41.942,-113.800,2.712,5.781,8.751,.131,66.086
 4742.000,41.845,29.177,72.497,-128.275,23.898,34.274,7.888,2.441,.073,.157,.152,64.496,-45.034,-112.235,2.705,5.779,8.842,.127,65.537
 4742.500,41.258,28.859,86.244,-126.450,24.237,34.651,7.887,2.445,.072,.155,.147,65.100,-48.990,-110.550,2.702,5.738,8.810,.121,64.682
 4743.000,40.382,28.431,96.773,-124.482,24.764,35.173,7.890,2.455,.073,.149,.141,68.235,-52.557,-108.722,2.703,5.713,8.776,.115,63.730
 4743.500,39.280,27.725,106.316,-122.344,25.458,36.069,7.889,2.467,.076,.142,.136,64.604,-55.308,-106.724,2.704,5.792,8.851,.108,62.817
 4744.000,38.020,26.775,113.143,-120.007,26.302,37.348,7.888,2.480,.078,.134,.130,60.080,-57.263,-104.527,2.706,5.862,8.978,.102,61.992
 4744.500,36.523,25.772,124.820,-117.452,27.380,38.802,7.881,2.493,.079,.127,.126,61.528,-58.395,-102.113,2.709,5.861,8.969,.097,61.211
 4745.000,34.826,24.819,133.111,-114.665,28.714,40.292,7.910,2.507,.079,.118,.123,58.468,-58.807,-99.465,2.715,5.824,8.909,.091,60.355
 4745.500,33.001,23.855,132.688,-111.629,30.302,41.919,8.004,2.522,.079,.110,.120,60.591,-58.659,-96.569,2.720,5.957,9.045,.085,59.564
 4746.000,30.773,22.741,138.879,-108.319,32.496,43.973,8.050,2.532,.079,.104,.117,62.018,-57.555,-93.399,2.724,6.494,9.459,.083,59.222
 4746.500,28.395,21.390,158.409,-104.711,35.217,46.750,8.048,2.534,.079,.103,.114,56.564,-55.443,-89.931,2.725,6.534,9.325,.084,59.431
 4747.000,26.292,19.868,158.136,-100.784,38.035,50.333,8.053,2.529,.079,.106,.114,47.144,-52.627,-86.144,2.725,5.984,8.845,.088,59.962
 4747.500,24.441,18.390,140.151,-96.534,40.915,54.379,8.064,2.521,.076,.111,.116,42.542,-49.373,-82.034,2.720,5.888,8.795,.091,60.370
 4748.000,22.937,17.216,131.399,-91.969,43.598,58.087,8.138,2.517,.071,.113,.117,42.408,-46.594,-77.609,2.718,6.042,8.937,.089,60.118
 4748.500,21.899,16.414,137.455,-87.103,45.663,60.924,8.212,2.523,.068,.109,.108,41.747,-44.977,-72.883,2.713,7.376,10.295,.081,58.965
 4749.000,21.426,15.848,152.745,-81.951,46.672,63.098,8.247,2.547,.066,.095,.088,40.697,-44.150,-67.871,2.707,18.021,18.942,.068,57.167
 4749.500,21.677,15.525,169.194,-76.542,46.132,64.413,8.242,2.586,.064,.073,.066,43.281,-43.060,-62.602,2.709,42.765,34.875,.055,55.238
 4750.000,22.542,15.717,149.606,-70.943,44.362,63.624,8.247,2.627,.060,.048,.051,53.541,-40.272,-57.143,2.721,52.877,38.620,.044,53.697
 4750.500,23.680,16.608,93.268,-65.271,42.230,60.214,8.253,2.656,.052,.032,.043,70.129,-34.860,-51.611,2.743,51.732,36.132,.038,52.913
 4751.000,24.965,18.099,61.608,-59.691,40.056,55.251,8.256,2.666,.043,.026,.039,78.232,-27.529,-46.171,2.813,55.370,37.675,.038,52.884
 4751.500,26.739,20.188,56.111,-54.380,37.399,49.533,8.262,2.665,.037,.026,.038,83.728,-20.518,-41.001,2.850,49.664,32.578,.041,53.366
 4752.000,29.392,23.143,45.731,-49.496,34.023,43.209,8.263,2.666,.036,.026,.040,88.366,-15.665,-36.256,2.882,40.674,27.634,.048,54.276
 4752.500,33.194,27.343,39.046,-45.149,30.126,36.572,8.251,2.671,.039,.023,.043,83.276,-13.161,-32.049,2.870,38.292,27.633,.058,55.682
 4753.000,39.289,33.294,37.947,-41.401,25.452,30.036,8.254,2.675,.043,.020,.047,74.997,-12.907,-28.441,2.777,32.622,24.187,.070,57.459
 4753.500,46.033,41.110,30.235,-38.281,21.724,24.325,8.260,2.676,.048,.020,.052,70.392,-11.824,-25.461,2.761,20.927,15.587,.084,59.345
 4754.000,51.080,49.734,19.187,-35.785,19.577,20.107,8.257,2.674,.051,.021,.059,77.410,-8.369,-23.105,2.801,19.684,13.183,.096,61.056
 4754.500,56.063,57.407,16.057,-33.887,17.837,17.420,8.249,2.675,.052,.020,.068,86.233,-5.796,-21.347,2.892,19.486,13.237,.104,62.187
 4755.000,60.538,62.725,16.621,-32.527,16.519,15.943,8.253,2.679,.052,.018,.075,106.098,-5.845,-20.127,2.999,19.680,13.900,.106,62.449
 4755.500,63.513,65.206,17.789,-31.615,15.745,15.336,8.260,2.684,.051,.015,.076,137.449,-8.644,-19.355,3.000,20.553,14.715,.102,61.904
 4756.000,65.873,64.989,19.082,-31.049,15.181,15.387,8.256,2.688,.049,.013,.074,161.334,-13.798,-18.929,3.000,20.730,15.193,.095,60.879
 4756.500,67.528,62.570,23.895,-30.730,14.809,15.982,8.252,2.686,.049,.014,.073,159.404,-19.441,-18.750,3.000,24.479,18.272,.088,59.894
 4757.000,69.337,59.472,29.168,-30.588,14.422,16.815,8.256,2.670,.050,.023,.072,159.933,-24.076,-18.748,3.000,29.410,23.115,.088,60.015
 4757.500,73.623,58.441,34.208,-30.576,13.583,17.111,8.253,2.636,.051,.043,.073,185.498,-27.138,-18.876,3.000,41.731,33.049,.106,62.465
 4758.000,80.866,62.511,34.274,-30.671,12.366,15.997,8.257,2.592,.054,.069,.080,226.251,-27.408,-19.111,3.000,37.371,29.286,.136,66.800
 4758.500,90.300,73.283,18.964,-30.850,11.074,13.646,8.256,2.554,.058,.091,.095,295.544,-24.031,-19.430,3.000,16.655,12.966,.166,70.966
 4759.000,101.872,88.993,8.973,-31.088,9.816,11.237,8.257,2.530,.060,.105,.113,367.155,-18.227,-19.808,3.000,9.935,7.565,.182,73.282
 4759.500,111.878,105.037,8.300,-31.355,8.938,9.521,8.261,2.521,.056,.111,.135,309.705,-11.743,-20.215,2.998,10.964,8.506,.183,73.379
 4760.000,122.424,118.478,9.939,-31.654,8.168,8.440,8.257,2.524,.053,.109,.154,189.156,-8.393,-20.654,2.995,12.659,9.535,.176,72.452
 4760.500,138.382,130.604,9.892,-32.048,7.226,7.657,8.255,2.535,.052,.102,.155,124.668,-9.578,-21.188,2.991,10.640,8.470,.173,71.973
 4761.000,155.382,142.892,8.104,-32.685,6.436,6.998,8.230,2.549,.055,.094,.145,102.748,-12.141,-21.965,2.985,9.271,7.524,.174,72.076
 4761.500,169.769,153.359,7.732,-33.806,5.890,6.521,8.187,2.560,.058,.088,.138,91.738,-14.391,-23.226,2.934,9.947,7.829,.175,72.230
 4762.000,182.379,159.447,8.691,-35.713,5.483,6.272,8.157,2.563,.057,.086,.135,90.844,-16.457,-25.273,2.927,10.539,8.412,.175,72.285
 4762.500,192.633,162.130,8.800,-38.725,5.191,6.168,8.148,2.554,.053,.091,.130,97.760,-18.043,-28.425,2.937,10.285,8.415,.176,72.374
 4763.000,204.199,164.791,7.932,-43.114,4.897,6.068,8.142,2.535,.048,.102,.122,96.665,-20.088,-32.954,2.904,10.004,8.102,.177,72.535
 4763.500,217.497,169.241,7.084,-49.008,4.598,5.909,8.128,2.518,.047,.112,.117,85.157,-23.543,-38.988,2.863,10.198,8.331,.178,72.682
 4764.000,229.881,174.754,7.522,-56.294,4.350,5.722,8.096,2.507,.052,.119,.114,73.975,-28.653,-46.414,2.758,10.650,9.437,.179,72.820
 4764.500,243.749,180.641,9.970,-64.551,4.103,5.536,8.088,2.499,.059,.124,.117,70.542,-35.190,-54.811,2.741,8.497,9.190,.181,73.122
 4765.000,261.830,187.988,12.625,-73.100,3.819,5.319,8.083,2.490,.067,.128,.125,64.827,-41.951,-63.500,2.735,5.987,7.821,.186,73.769
 4765.500,280.713,197.971,13.200,-81.168,3.562,5.051,8.086,2.483,.073,.133,.139,60.941,-47.226,-71.708,2.739,5.200,7.152,.192,74.706
 4766.000,299.324,209.682,12.488,-88.102,3.341,4.769,8.083,2.477,.079,.137,.155,61.294,-50.780,-78.782,2.748,5.011,6.926,.199,75.611
 4766.500,320.068,220.910,12.014,-93.538,3.124,4.527,8.090,2.473,.085,.139,.167,66.388,-53.532,-84.358,2.750,4.959,6.868,.203,76.200
 4767.000,339.234,230.345,12.065,-97.438,2.948,4.341,8.095,2.470,.089,.140,.169,67.756,-55.675,-88.398,2.746,4.964,6.876,.205,76.447
 4767.500,354.957,238.259,12.315,-100.005,2.817,4.197,8.082,2.466,.091,.143,.165,68.582,-57.326,-91.105,2.737,4.928,6.830,.205,76.567
 4768.000,370.382,245.316,12.364,-101.542,2.700,4.076,8.080,2.460,.090,.147,.163,71.254,-58.797,-92.782,2.729,4.920,6.801,.207,76.787
 4768.500,383.316,251.498,12.217,-102.341,2.609,3.976,8.087,2.451,.088,.152,.161,66.861,-59.721,-93.721,2.721,4.913,6.785,.210,77.194
 4769.000,393.402,256.556,11.903,-102.625,2.542,3.898,8.087,2.438,.084,.159,.162,68.562,-60.052,-94.145,2.713,4.875,6.734,.214,77.779
 4769.500,403.210,260.583,11.490,-102.546,2.480,3.838,8.085,2.422,.079,.168,.168,74.574,-60.154,-94.206,2.711,4.850,6.682,.218,78.399
 4770.000,412.290,263.908,11.258,-102.211,2.425,3.789,8.089,2.407,.074,.177,.182,71.719,-60.125,-94.011,2.716,4.820,6.599,.221,78.815
 4770.500,420.544,267.140,11.012,-101.702,2.378,3.743,8.126,2.398,.070,.182,.192,68.158,-60.091,-93.642,2.722,4.811,6.537,.222,78.908
 4771.000,429.307,271.118,10.678,-101.086,2.329,3.688,8.145,2.398,.069,.183,.195,69.029,-60.274,-93.166,2.724,4.940,6.723,.221,78.709
 4771.500,435.498,276.247,10.663,-100.413,2.296,3.620,8.181,2.406,.069,.178,.191,77.692,-60.434,-92.633,2.725,5.162,7.046,.218,78.309
 4772.000,439.129,282.039,10.758,-99.704,2.277,3.546,8.194,2.420,.070,.169,.184,82.993,-60.542,-92.064,2.728,5.157,7.080,.215,77.863
 4772.500,441.751,287.531,10.696,-98.947,2.264,3.478,8.233,2.438,.071,.159,.180,78.453,-60.666,-91.447,2.736,4.972,6.850,.212,77.485
 4773.000,443.628,291.846,10.604,-98.109,2.254,3.427,8.252,2.455,.071,.149,.178,73.896,-60.784,-90.749,2.744,4.877,6.686,.209,77.097
 4773.500,445.336,294.577,10.626,-97.156,2.246,3.395,8.266,2.465,.070,.143,.178,76.172,-60.921,-89.936,2.751,4.865,6.640,.206,76.685
 4774.000,446.657,295.879,10.720,-96.075,2.239,3.380,8.296,2.468,.068,.141,.179,75.393,-60.980,-88.995,2.755,4.865,6.654,.205,76.453
 4774.500,446.252,296.275,10.805,-94.874,2.241,3.375,8.348,2.467,.066,.142,.177,80.611,-60.692,-87.934,2.753,4.881,6.664,.205,76.511
 4775.000,444.265,296.436,10.703,-93.562,2.251,3.373,8.372,2.463,.062,.145,.170,74.020,-59.949,-86.762,2.745,4.880,6.610,.207,76.758
 4775.500,440.296,296.785,10.276,-92.115,2.271,3.369,8.395,2.462,.058,.145,.165,64.874,-58.764,-85.455,2.740,4.879,6.552,.209,77.080
 4776.000,433.572,297.051,9.670,-90.463,2.306,3.366,8.430,2.468,.056,.141,.165,70.077,-57.322,-83.943,2.746,4.969,6.653,.211,77.334
 4776.500,425.538,296.408,9.553,-88.496,2.350,3.374,8.443,2.484,.058,.132,.168,75.053,-56.036,-82.116,2.760,5.015,6.730,.211,77.298
 4777.000,417.390,294.322,9.738,-86.097,2.396,3.398,8.441,2.499,.062,.123,.175,77.354,-55.087,-79.857,2.779,4.979,6.707,.207,76.857
 4777.500,408.855,291.256,9.943,-83.181,2.446,3.433,8.454,2.508,.064,.118,.185,80.629,-54.251,-77.081,2.798,5.068,6.813,.202,76.125
 4778.000,400.979,288.179,9.984,-79.723,2.494,3.470,8.457,2.508,.064,.118,.183,79.366,-53.349,-73.763,2.798,5.465,7.213,.197,75.376
 4778.500,391.266,285.443,9.745,-75.775,2.556,3.503,8.519,2.501,.061,.122,.170,75.293,-51.959,-69.955,2.787,5.901,7.580,.193,74.824
 4779.000,378.484,282.451,9.505,-71.442,2.642,3.540,8.547,2.492,.057,.127,.167,76.260,-49.882,-65.762,2.785,5.981,7.688,.190,74.448
 4779.500,364.196,278.333,9.413,-66.853,2.746,3.593,8.538,2.485,.055,.132,.172,71.727,-47.230,-61.313,2.792,6.471,8.144,.188,74.080
 4780.000,348.280,272.692,9.065,-62.121,2.871,3.667,8.549,2.483,.053,.133,.170,68.561,-43.981,-56.721,2.780,8.599,9.652,.185,73.619
 4780.500,331.864,265.563,8.312,-57.334,3.013,3.766,8.563,2.486,.052,.131,.164,72.519,-40.395,-52.074,2.787,12.592,11.525,.181,73.087
 4781.000,316.789,256.847,7.813,-52.564,3.157,3.893,8.561,2.494,.052,.126,.158,74.280,-36.993,-47.444,2.790,16.191,11.875,.177,72.551
 4781.500,301.434,246.079,7.747,-47.887,3.318,4.064,8.559,2.503,.053,.121,.153,67.734,-33.880,-42.908,2.771,17.486,10.995,.174,72.079
 4782.000,285.583,233.133,7.696,-43.385,3.502,4.289,8.549,2.513,.053,.115,.148,69.595,-31.175,-38.545,2.775,15.509,9.544,.171,71.713
 4782.500,270.594,218.767,7.470,-39.132,3.696,4.571,8.553,2.524,.053,.109,.142,76.479,-29.117,-34.432,2.795,12.224,8.349,.169,71.429
 4783.000,255.529,204.038,7.597,-35.175,3.914,4.901,8.560,2.534,.051,.103,.138,80.578,-27.510,-30.615,2.848,11.557,8.365,.167,71.194
 4783.500,243.312,190.484,8.185,-31.528,4.110,5.250,8.566,2.540,.050,.099,.136,79.457,-26.452,-27.108,2.831,11.954,8.875,.167,71.176
 4784.000,237.081,180.470,8.693,-28.191,4.218,5.541,8.572,2.541,.050,.099,.139,83.392,-25.853,-23.911,2.871,11.663,8.922,.172,71.770
 4784.500,237.053,176.518,8.780,-25.176,4.219,5.665,8.568,2.538,.049,.101,.150,91.828,-25.123,-21.036,2.934,10.738,8.347,.182,73.272
 4785.000,244.465,180.749,8.158,-22.534,4.091,5.532,8.586,2.530,.050,.105,.171,105.610,-24.099,-18.534,3.000,9.081,7.160,.199,75.636
 4785.500,257.316,194.157,6.864,-20.364,3.886,5.150,8.650,2.521,.055,.110,.200,109.335,-22.566,-16.504,3.000,7.114,5.732,.220,78.567
 4786.000,273.300,215.297,5.784,-18.792,3.659,4.645,8.845,2.518,.069,.112,.226,104.189,-20.855,-15.072,3.000,5.267,4.697,.241,81.571
 4786.500,289.432,239.454,5.270,-17.938,3.455,4.176,9.032,2.529,.091,.106,.239,99.296,-19.671,-14.358,2.994,4.166,4.195,.256,83.692
 4787.000,303.849,260.636,4.887,-17.877,3.291,3.837,8.839,2.553,.116,.092,.246,95.366,-19.939,-14.437,2.962,4.173,3.996,.257,83.844
 4787.500,316.151,274.528,4.843,-18.603,3.163,3.643,8.458,2.579,.130,.076,.252,90.740,-22.198,-15.303,2.973,6.327,4.348,.242,81.776
 4788.000,326.354,279.595,5.669,-19.998,3.064,3.577,8.419,2.598,.128,.066,.258,83.908,-25.957,-16.838,2.980,9.776,5.696,.217,78.223
 4788.500,332.247,278.161,6.761,-21.817,3.010,3.595,8.413,2.600,.112,.064,.262,70.072,-29.661,-18.797,2.953,13.949,7.815,.192,74.613
 4789.000,331.540,275.148,7.504,-23.698,3.016,3.634,8.395,2.589,.091,.071,.263,58.548,-31.994,-20.818,2.931,16.056,9.324,.178,72.664
 4789.500,325.088,272.962,7.549,-25.236,3.076,3.664,8.422,2.575,.078,.079,.260,57.723,-33.562,-22.496,2.918,13.658,8.860,.181,73.154
 4790.000,310.799,268.922,6.873,-26.120,3.217,3.719,8.406,2.572,.076,.080,.249,69.307,-37.572,-23.520,2.917,8.895,6.499,.190,74.419
 4790.500,281.637,257.426,5.718,-26.264,3.551,3.885,8.313,2.593,.083,.068,.217,90.826,-47.789,-23.804,2.936,5.849,5.291,.184,73.538
 4791.000,247.398,232.682,6.210,-25.842,4.042,4.298,8.264,2.632,.090,.046,.151,93.808,-64.322,-23.522,2.950,13.168,12.821,.155,69.385
 4791.500,219.658,193.701,17.702,-25.192,4.552,5.163,8.259,2.671,.088,.023,.099,74.716,-82.879,-23.012,2.815,39.517,40.366,.108,62.794
 4792.000,191.558,149.421,48.412,-24.643,5.220,6.693,8.252,2.691,.076,.011,.062,59.895,-98.067,-22.603,2.776,55.467,60.084,.059,55.842
 4792.500,161.312,112.045,87.036,-24.374,6.199,8.925,8.245,2.693,.060,.010,.044,53.618,-107.582,-22.474,2.753,52.813,58.303,.026,51.148
 4793.000,135.592,84.677,145.489,-24.388,7.375,11.810,8.243,2.689,.051,.012,.035,43.019,-112.246,-22.628,2.740,50.789,55.496,.014,49.413
 4793.500,108.411,62.532,196.252,-24.571,9.224,15.992,8.251,2.690,.049,.012,.032,33.958,-110.111,-22.951,2.735,45.638,53.185,.013,49.304
 4794.000,79.469,43.394,200.942,-24.789,12.583,23.045,8.253,2.696,.051,.008,.030,30.741,-99.956,-23.309,2.737,45.685,56.121,.015,49.659
 4794.500,59.182,29.517,170.815,-24.942,16.897,33.879,8.249,2.700,.053,.006,.029,34.017,-86.369,-23.602,2.739,64.578,65.539,.018,50.085
 4795.000,47.369,21.870,133.795,-24.985,21.111,45.724,8.251,2.696,.052,.008,.029,41.809,-72.680,-23.785,2.736,77.128,70.455,.022,50.544
 4795.500,40.181,18.667,99.174,-24.917,24.887,53.570,8.248,2.684,.048,.015,.029,46.890,-60.330,-23.857,2.728,63.110,57.047,.025,50.982
 4796.000,37.142,17.754,75.656,-24.756,26.924,56.326,8.255,2.673,.045,.021,.029,50.257,-53.205,-23.836,2.723,58.060,52.385,.026,51.164
 4796.500,36.309,17.737,83.902,-24.529,27.541,56.381,8.254,2.673,.045,.022,.028,50.597,-52.170,-23.749,2.722,65.287,60.685,.025,50.971
 4797.000,35.071,17.929,107.509,-24.259,28.513,55.776,8.247,2.680,.047,.018,.027,47.724,-53.761,-23.619,2.724,71.395,66.239,.022,50.589
 4797.500,33.419,18.084,138.885,-23.962,29.923,55.297,8.253,2.682,.048,.016,.026,50.981,-55.253,-23.462,2.725,76.934,72.408,.020,50.287
 4798.000,31.859,18.110,160.409,-23.649,31.388,55.217,8.255,2.675,.045,.020,.025,57.450,-55.401,-23.289,2.722,77.161,74.928,.019,50.155
 4798.500,29.880,17.864,126.333,-23.322,33.467,55.978,8.250,2.667,.042,.025,.024,62.966,-53.844,-23.102,2.720,67.105,61.399,.018,50.096
 4799.000,27.407,17.142,99.970,-22.977,36.487,58.337,8.246,2.664,.039,.027,.024,71.171,-52.189,-22.897,2.736,62.257,52.380,.017,49.948
 4799.500,24.855,15.878,128.552,-22.601,40.233,62.978,8.240,2.665,.038,.026,.023,72.850,-52.110,-22.661,2.744,69.151,60.842,.015,49.623
 4800.000,22.397,14.323,184.847,-22.176,44.649,69.818,8.237,2.667,.036,.025,.021,67.863,-52.836,-22.376,2.723,75.826,71.390,.012,49.218
 4800.500,20.194,12.896,217.909,-21.685,49.519,77.541,8.254,2.671,.035,.023,.019,66.074,-52.712,-22.025,2.721,76.806,73.988,.010,48.916
 4801.000,18.188,11.815,224.211,-21.109,54.980,84.637,8.280,2.679,.037,.018,.018,67.496,-50.550,-21.589,2.725,78.291,76.031,.009,48.750
 4801.500,16.346,11.024,207.714,-20.440,61.175,90.707,8.281,2.688,.041,.013,.018,64.447,-46.245,-21.060,2.725,73.905,70.384,.008,48.687
 4802.000,15.388,10.504,190.573,-19.676,64.985,95.201,8.274,2.697,.046,.007,.018,58.863,-42.082,-20.436,2.729,62.297,59.971,.009,48.774
 4802.500,16.023,10.492,189.799,-18.832,62.409,95.313,8.280,2.701,.049,.005,.021,60.606,-40.376,-19.732,2.734,54.394,53.125,.012,49.130
 4803.000,18.653,11.501,164.304,-17.930,53.612,86.948,8.294,2.697,.048,.007,.024,67.450,-41.207,-18.970,2.739,59.988,53.130,.018,50.073
 4803.500,23.539,14.382,138.489,-17.004,42.482,69.531,8.332,2.687,.044,.013,.030,88.324,-42.676,-18.184,2.908,67.858,60.804,.032,51.985
 4804.000,30.018,20.091,99.928,-16.089,33.313,49.774,8.358,2.675,.041,.020,.037,128.463,-41.413,-17.409,3.000,62.809,57.312,.050,54.596
 4804.500,36.593,28.351,43.173,-15.214,27.327,35.272,8.382,2.664,.041,.027,.046,169.167,-35.357,-16.674,3.000,37.916,32.276,.068,57.063
 4805.000,44.010,37.181,21.999,-14.398,22.722,26.895,8.373,2.653,.042,.033,.056,172.023,-27.307,-15.998,3.000,26.517,19.907,.081,58.987
 4805.500,53.940,45.589,27.408,-13.647,18.539,21.935,8.417,2.641,.042,.041,.069,152.993,-21.337,-15.387,3.000,35.101,25.491,.092,60.460
 4806.000,67.457,55.428,25.889,-12.956,14.824,18.041,8.437,2.624,.041,.051,.078,183.270,-19.108,-14.836,3.000,33.993,24.216,.102,61.994
 4806.500,85.319,69.073,17.790,-12.315,11.721,14.477,8.440,2.602,.037,.063,.085,219.781,-19.094,-14.335,3.000,32.852,22.213,.119,64.378
 4807.000,104.478,87.398,13.701,-11.713,9.571,11.442,8.460,2.581,.034,.076,.096,171.686,-17.903,-13.873,3.000,25.254,17.340,.142,67.658
 4807.500,123.671,109.625,10.028,-11.146,8.086,9.122,8.525,2.563,.032,.086,.114,116.665,-15.412,-13.446,3.000,13.398,9.384,.167,71.064
 4808.000,141.140,132.655,8.070,-10.615,7.085,7.538,8.554,2.550,.032,.093,.135,99.600,-12.898,-13.055,2.997,9.184,6.923,.185,73.721
 4808.500,154.610,152.441,7.288,-10.131,6.468,6.560,8.558,2.543,.034,.098,.155,106.103,-11.864,-12.711,3.000,7.828,6.208,.195,75.095
 4809.000,164.642,166.217,7.636,-9.710,6.074,6.016,8.566,2.544,.038,.097,.165,125.133,-13.709,-12.430,3.000,9.283,6.735,.195,75.025
 4809.500,171.480,172.578,8.259,-9.372,5.832,5.794,8.562,2.555,.043,.091,.159,150.184,-18.345,-12.232,3.000,9.864,7.010,.183,73.428
 4810.000,173.774,171.160,8.853,-9.120,5.755,5.843,8.583,2.573,.049,.080,.145,154.210,-24.080,-12.120,3.000,10.016,7.750,.165,70.816
 4810.500,173.893,163.305,12.750,-8.943,5.751,6.123,8.628,2.592,.054,.069,.134,133.814,-29.247,-11.883,3.000,14.964,11.486,.148,68.467
 4811.000,173.214,153.215,17.123,-8.818,5.773,6.527,8.638,2.604,.057,.062,.126,122.293,-32.046,-11.697,3.000,17.470,13.545,.140,67.324
 4811.500,171.676,146.289,15.870,-8.725,5.825,6.836,8.630,2.606,.058,.061,.123,103.696,-31.372,-11.544,3.000,13.672,11.213,.143,67.677
 4812.000,169.701,144.569,11.572,-8.654,5.893,6.917,8.627,2.601,.061,.064,.125,92.087,-27.646,-11.413,2.936,9.488,8.258,.154,69.223
 4812.500,167.019,145.693,8.838,-8.606,5.987,6.864,8.635,2.599,.067,.065,.136,87.447,-22.451,-11.304,2.901,8.172,7.103,.166,70.931
 4813.000,165.653,146.889,8.305,-8.590,6.037,6.808,8.636,2.604,.073,.062,.150,84.828,-18.398,-11.227,2.882,8.496,7.298,.172,71.836
 4813.500,169.895,148.348,8.727,-8.616,5.886,6.741,8.629,2.609,.073,.059,.159,83.258,-17.596,-11.194,2.874,9.334,7.982,.172,71.848
 4814.000,181.053,152.303,9.465,-8.696,5.523,6.566,8.626,2.603,.067,.063,.159,80.871,-19.604,-11.213,2.864,9.709,8.207,.171,71.666
 4814.500,196.276,160.256,9.742,-8.834,5.095,6.240,8.630,2.586,.057,.072,.159,87.459,-22.269,-11.291,2.901,8.935,7.934,.174,72.137
 4815.000,211.621,172.251,9.164,-9.034,4.725,5.806,8.626,2.571,.051,.081,.171,96.185,-23.868,-11.431,2.969,8.186,7.415,.184,73.592
 4815.500,226.221,187.648,8.173,-9.303,4.420,5.329,8.629,2.563,.050,.086,.193,99.381,-24.228,-11.639,2.995,7.371,6.475,.200,75.777
 4816.000,241.571,205.253,7.391,-9.649,4.140,4.872,8.635,2.558,.054,.089,.215,98.399,-24.109,-11.925,2.987,6.672,5.807,.217,78.150
 4816.500,255.906,223.868,6.950,-10.078,3.908,4.467,8.636,2.551,.059,.093,.227,97.612,-23.798,-12.294,2.980,6.263,5.501,.231,80.239
 4817.000,269.631,242.451,6.679,-10.577,3.709,4.125,8.671,2.546,.066,.096,.239,99.862,-23.756,-12.732,2.999,5.776,5.139,.243,81.884
 4817.500,281.078,258.352,6.437,-11.110,3.558,3.871,8.683,2.543,.076,.098,.250,100.992,-24.059,-13.205,3.000,5.113,4.874,.252,83.143
 4818.000,284.625,267.076,6.220,-11.623,3.513,3.744,8.661,2.543,.087,.098,.256,99.863,-24.726,-13.658,2.999,4.518,4.735,.256,83.675
 4818.500,277.849,263.878,5.978,-12.065,3.599,3.790,8.671,2.550,.097,.094,.246,95.427,-26.966,-14.039,2.963,4.214,4.377,.246,82.305
 4819.000,261.308,245.658,5.957,-12.403,3.827,4.071,8.616,2.565,.103,.085,.220,83.452,-31.833,-14.317,2.912,4.721,4.534,.217,78.253
 4819.500,239.356,214.923,7.967,-12.644,4.178,4.653,8.378,2.586,.098,.072,.182,69.195,-38.428,-14.497,2.852,8.373,6.668,.176,72.362
 4820.000,218.375,179.951,14.907,-12.827,4.579,5.557,8.356,2.607,.085,.060,.143,56.962,-44.673,-14.620,2.810,15.115,10.085,.133,66.340
 4820.500,197.335,148.124,21.951,-13.014,5.068,6.751,8.353,2.621,.070,.052,.108,49.521,-48.438,-14.747,2.777,21.373,13.197,.103,62.025
 4821.000,172.043,121.645,21.254,-13.267,5.813,8.221,8.378,2.627,.061,.049,.083,45.349,-49.062,-14.940,2.751,20.329,12.246,.089,60.090
 4821.500,144.627,98.758,18.838,-13.627,6.914,10.126,8.321,2.628,.058,.048,.068,45.543,-48.530,-15.239,2.736,14.540,10.336,.083,59.189
 4822.000,113.870,78.081,20.126,-14.098,8.782,12.807,8.255,2.627,.060,.049,.062,45.429,-46.960,-15.650,2.727,13.001,11.267,.074,58.008
 4822.500,86.271,60.689,33.109,-14.644,11.591,16.478,8.215,2.619,.061,.053,.058,41.191,-43.949,-16.135,2.718,22.551,18.294,.065,56.717
 4823.000,69.814,48.127,57.585,-15.197,14.324,20.778,8.189,2.611,.066,.058,.057,37.893,-40.870,-16.628,2.711,32.123,27.712,.059,55.912
 4823.500,61.686,40.712,58.505,-15.677,16.211,24.563,8.183,2.612,.078,.058,.057,43.208,-37.072,-17.048,2.714,28.476,25.462,.059,55.884
 4824.000,57.521,37.403,34.340,-16.015,17.385,26.736,8.186,2.624,.095,.050,.059,52.306,-31.949,-17.325,2.727,16.153,14.098,.065,56.636
 4824.500,54.729,36.477,25.816,-16.178,18.272,27.414,8.200,2.640,.108,.041,.060,57.223,-27.532,-17.428,2.740,13.930,11.706,.070,57.434
 4825.000,50.910,36.202,28.665,-16.172,19.643,27.622,8.188,2.652,.110,.034,.060,61.414,-27.256,-17.361,2.748,19.109,14.014,.070,57.359
 4825.500,46.113,34.974,30.911,-16.035,21.686,28.593,8.159,2.661,.101,.029,.054,66.509,-33.424,-17.164,2.749,28.688,18.784,.063,56.364
 4826.000,42.842,31.710,43.153,-15.811,23.341,31.536,8.156,2.671,.088,.023,.047,60.383,-44.806,-16.880,2.745,46.761,33.676,.051,54.739
 4826.500,40.851,26.596,92.164,-15.536,24.479,37.599,8.163,2.683,.077,.016,.041,47.721,-56.388,-16.544,2.742,70.136,50.472,.037,52.795
 4827.000,38.687,21.314,169.047,-15.227,25.849,46.918,8.160,2.693,.068,.010,.035,38.314,-63.642,-16.175,2.742,78.246,51.465,.026,51.185
 4827.500,39.925,18.514,201.995,-14.890,25.047,54.014,8.165,2.694,.062,.009,.031,37.035,-68.739,-15.778,2.738,78.208,50.593,.021,50.512
 4828.000,46.612,21.423,181.003,-14.529,21.454,46.679,8.169,2.677,.056,.019,.032,45.149,-72.638,-15.357,2.726,78.813,49.190,.026,51.220
 4828.500,58.279,33.495,121.265,-14.155,17.159,29.855,8.164,2.637,.051,.043,.038,76.272,-73.183,-14.922,2.785,64.296,37.062,.048,54.236
 4829.000,77.447,56.988,55.207,-13.788,12.912,17.548,8.160,2.582,.054,.075,.049,116.534,-70.714,-14.495,3.000,43.016,22.759,.090,60.304
 4829.500,97.955,90.744,22.760,-13.453,10.209,11.020,8.187,2.539,.068,.100,.069,138.437,-63.898,-14.100,3.000,22.986,11.754,.139,67.214
 4830.000,106.254,125.557,9.548,-13.168,9.411,7.964,8.181,2.531,.087,.105,.088,151.325,-57.877,-13.755,3.000,12.335,8.105,.164,70.746
 4830.500,104.376,144.043,9.908,-12.929,9.581,6.942,8.155,2.556,.097,.090,.090,143.212,-63.548,-13.455,3.000,38.793,26.935,.153,69.211
 4831.000,103.631,136.482,45.894,-12.709,9.650,7.327,8.160,2.595,.092,.067,.072,100.871,-76.832,-13.174,3.000,82.430,61.231,.114,63.606
 4831.500,107.119,113.129,141.157,-12.461,9.335,8.840,8.156,2.631,.076,.046,.050,68.769,-88.045,-12.866,2.734,93.278,71.269,.066,56.877
 4832.000,113.579,92.101,169.713,-12.145,8.804,10.858,8.155,2.651,.063,.035,.039,69.204,-92.826,-12.489,2.735,81.563,59.231,.040,53.132
 4832.500,119.139,81.270,85.961,-11.734,8.394,12.305,8.157,2.658,.059,.030,.036,96.059,-89.303,-12.019,2.968,53.602,37.242,.044,53.772
 4833.000,116.350,78.357,35.371,-11.234,8.595,12.762,8.180,2.658,.064,.030,.040,112.715,-75.995,-11.458,3.000,34.474,22.966,.068,57.142
 4833.500,109.482,81.615,23.758,-10.669,9.134,12.253,8.228,2.652,.070,.034,.048,105.595,-56.262,-10.833,3.000,28.085,17.452,.097,61.263
 4834.000,111.904,92.084,13.868,-10.075,8.936,10.860,8.218,2.637,.072,.043,.062,97.416,-38.008,-10.179,2.979,16.633,11.480,.126,65.342
 4834.500,125.225,110.281,10.719,-9.486,7.986,9.068,8.258,2.614,.070,.056,.084,96.029,-25.212,-9.529,2.968,14.777,11.084,.155,69.369
 4835.000,147.600,134.971,9.722,-8.933,6.775,7.409,8.277,2.588,.067,.071,.111,96.378,-18.612,-8.916,2.970,9.987,8.251,.181,73.133
 4835.500,177.537,162.492,7.234,-8.447,5.633,6.154,8.329,2.570,.068,.082,.135,87.396,-16.983,-8.369,2.901,6.492,5.742,.206,76.579
 4836.000,209.166,188.671,6.747,-8.049,4.781,5.300,8.323,2.564,.074,.085,.156,82.335,-17.860,-7.911,2.863,5.567,5.231,.225,79.340
 4836.500,234.298,210.746,6.503,-7.753,4.268,4.745,8.331,2.566,.081,.084,.173,87.427,-19.384,-7.555,2.901,4.939,5.062,.235,80.736
 4837.000,252.711,226.622,6.514,-7.557,3.957,4.413,8.349,2.569,.081,.082,.189,99.531,-21.346,-7.298,2.996,5.262,5.247,.236,80.907
 4837.500,266.389,236.191,6.879,-7.451,3.754,4.234,8.344,2.572,.075,.080,.201,106.485,-23.440,-7.132,3.000,5.951,5.761,.233,80.514
 4838.000,276.546,241.918,7.125,-7.428,3.616,4.134,8.333,2.576,.067,.078,.206,106.114,-25.118,-7.048,3.000,6.344,6.096,.230,80.115
 4838.500,281.875,246.170,7.113,-7.479,3.548,4.062,8.330,2.578,.059,.077,.212,101.620,-25.844,-7.039,3.000,6.644,6.015,.230,80.111
 4839.000,281.402,249.161,6.843,-7.604,3.554,4.014,8.331,2.575,.053,.079,.220,94.030,-26.040,-7.104,2.952,6.712,5.882,.233,80.495
 4839.500,273.250,248.364,6.349,-7.805,3.660,4.026,8.341,2.569,.050,.083,.217,96.448,-27.428,-7.245,2.971,6.357,5.617,.232,80.389
 4840.000,252.554,239.002,5.952,-8.090,3.960,4.184,8.328,2.569,.049,.082,.188,90.959,-31.824,-7.469,2.928,5.856,5.369,.218,78.333
 4840.500,225.895,217.196,6.797,-8.464,4.427,4.604,8.293,2.583,.051,.074,.143,79.741,-39.856,-7.783,2.836,9.233,6.690,.186,73.797
 4841.000,204.445,184.500,12.816,-8.918,4.891,5.420,8.282,2.604,.052,.062,.104,60.635,-49.651,-8.177,2.767,21.391,12.379,.144,67.808
 4841.500,183.639,148.797,27.025,-9.428,5.445,6.721,8.324,2.625,.051,.049,.071,46.556,-56.878,-8.626,2.738,33.408,19.583,.102,61.940
 4842.000,160.574,118.463,36.728,-9.952,6.228,8.441,8.339,2.642,.050,.040,.053,42.870,-59.413,-9.090,2.727,36.577,22.562,.071,57.606
 4842.500,137.398,94.984,32.605,-10.442,7.278,10.528,8.342,2.655,.049,.032,.046,41.307,-58.004,-9.519,2.727,32.855,20.758,.056,55.449
 4843.000,111.468,75.085,31.543,-10.848,8.971,13.318,8.364,2.668,.049,.024,.044,41.698,-52.834,-9.865,2.735,35.905,22.729,.051,54.769
 4843.500,87.715,58.481,36.683,-11.126,11.401,17.100,8.385,2.681,.050,.017,.044,39.758,-45.793,-10.082,2.744,39.305,25.144,.049,54.466
 4844.000,77.469,48.485,40.541,-11.246,12.908,20.625,8.381,2.691,.052,.011,.045,39.109,-42.301,-10.143,2.752,41.768,28.722,.048,54.333
 4844.500,78.382,47.643,45.923,-11.210,12.758,20.989,8.379,2.697,.053,.008,.048,42.031,-41.917,-10.046,2.761,48.187,32.989,.053,54.968
 4845.000,84.811,55.988,42.342,-11.059,11.791,17.861,8.399,2.693,.052,.010,.055,45.901,-40.738,-9.834,2.767,45.669,27.708,.066,56.897
 4845.500,94.051,70.953,26.327,-10.870,10.632,14.094,8.427,2.678,.050,.019,.066,61.776,-36.807,-9.585,2.771,27.697,16.720,.087,59.877
 4846.000,100.046,87.054,13.912,-10.735,9.995,11.487,8.435,2.658,.047,.030,.080,82.646,-29.173,-9.390,2.866,13.657,9.386,.108,62.732
 4846.500,101.328,97.461,8.847,-10.725,9.869,10.260,8.444,2.645,.045,.038,.094,81.129,-21.971,-9.320,2.855,11.761,8.879,.117,64.071
 4847.000,104.677,99.352,10.011,-10.860,9.553,10.065,8.464,2.641,.047,.040,.098,73.367,-22.063,-9.395,2.795,21.896,17.065,.113,63.555
 4847.500,113.541,97.623,19.689,-11.112,8.807,10.243,8.463,2.636,.054,.043,.092,61.712,-28.378,-9.586,2.773,35.931,28.816,.106,62.537
 4848.000,127.419,100.496,30.482,-11.428,7.848,9.951,8.457,2.613,.065,.057,.085,53.448,-34.614,-9.842,2.748,32.974,25.433,.110,63.133
 4848.500,144.317,112.449,23.338,-11.765,6.929,8.893,8.506,2.578,.083,.077,.084,62.785,-36.459,-10.119,2.733,20.111,13.924,.132,66.166
 4849.000,155.672,130.941,10.566,-12.117,6.424,7.637,8.573,2.552,.105,.092,.091,78.012,-31.449,-10.410,2.810,8.104,6.844,.161,70.348
 4849.500,160.648,148.908,6.295,-12.510,6.225,6.715,8.566,2.547,.122,.096,.107,93.209,-22.163,-10.742,2.945,5.452,5.443,.186,73.773
 4850.000,166.708,161.751,6.693,-12.992,5.998,6.182,8.582,2.555,.123,.091,.131,96.323,-14.588,-11.164,2.970,7.488,6.488,.197,75.353
 4850.500,179.332,171.444,7.603,-13.606,5.576,5.833,8.592,2.564,.111,.085,.162,85.857,-12.406,-11.718,2.889,8.423,7.070,.197,75.432
 4851.000,198.330,182.411,7.705,-14.371,5.042,5.482,8.618,2.569,.094,.082,.182,79.891,-14.115,-12.423,2.863,7.898,6.762,.197,75.406
 4851.500,221.960,196.126,7.148,-15.273,4.505,5.099,8.628,2.571,.086,.081,.199,82.573,-16.876,-13.265,2.888,7.280,6.289,.203,76.168
 4852.000,243.031,210.984,6.483,-16.273,4.115,4.740,8.634,2.572,.087,.081,.226,91.700,-18.459,-14.204,2.937,6.722,6.050,.213,77.599
 4852.500,257.789,225.204,6.071,-17.314,3.879,4.440,8.636,2.565,.088,.085,.252,93.026,-18.641,-15.185,2.963,6.644,5.798,.224,79.168
 4853.000,271.139,238.492,5.821,-18.340,3.688,4.193,8.664,2.545,.085,.097,.270,94.329,-18.706,-16.150,2.977,6.503,5.488,.233,80.489
 4853.500,286.244,251.142,5.636,-19.294,3.493,3.982,8.796,2.510,.081,.117,.280,97.602,-19.277,-17.044,2.988,5.795,5.165,.240,81.464
 4854.000,302.591,263.683,5.532,-20.128,3.305,3.792,8.839,2.470,.083,.140,.285,96.721,-20.149,-17.818,2.986,4.305,4.744,.246,82.292
 4854.500,318.644,276.988,5.439,-20.804,3.138,3.610,9.053,2.440,.100,.158,.287,97.397,-20.930,-18.434,2.989,3.777,4.459,.254,83.506
 4855.000,335.297,290.857,5.217,-21.299,2.982,3.438,9.437,2.429,.128,.165,.286,100.099,-21.671,-18.868,3.000,3.619,4.229,.267,85.230
 4855.500,349.393,303.213,4.909,-21.607,2.862,3.298,9.421,2.437,.156,.160,.285,101.677,-22.185,-19.116,3.000,3.289,3.925,.279,86.909
 4856.000,359.414,311.694,4.731,-21.742,2.782,3.208,9.429,2.460,.173,.146,.287,98.487,-22.661,-19.190,2.994,3.167,3.746,.286,87.968
 4856.500,366.171,315.492,4.818,-21.737,2.731,3.170,9.381,2.490,.176,.129,.288,98.841,-23.417,-19.125,2.995,3.268,3.906,.286,87.942
 4857.000,369.878,315.569,5.036,-21.645,2.704,3.169,9.155,2.521,.169,.110,.286,97.980,-24.385,-18.973,2.992,3.595,4.099,.278,86.838
 4857.500,370.174,313.565,5.204,-21.529,2.701,3.189,9.123,2.547,.158,.095,.290,91.625,-25.235,-18.796,3.006,3.758,4.174,.268,85.481
 4858.000,365.847,310.316,5.313,-21.451,2.733,3.223,8.998,2.563,.147,.086,.301,84.581,-25.664,-18.658,3.034,3.768,4.200,.262,84.523
 4858.500,356.428,305.024,5.348,-21.466,2.806,3.278,8.860,2.570,.133,.082,.299,85.062,-25.813,-18.612,3.035,3.927,4.317,.256,83.781
 4859.000,342.804,295.301,5.346,-21.616,2.917,3.386,8.910,2.577,.119,.078,.272,86.100,-26.395,-18.702,2.988,4.036,4.450,.248,82.597
 4859.500,322.923,278.193,5.419,-21.933,3.097,3.595,8.872,2.593,.108,.068,.237,86.197,-27.789,-18.959,2.957,4.605,4.845,.232,80.380
 4860.000,299.454,252.773,6.309,-22.424,3.339,3.956,8.602,2.615,.098,.056,.205,82.578,-30.126,-19.390,2.931,7.430,6.422,.210,77.159
 4860.500,276.697,222.391,8.451,-23.063,3.614,4.497,8.581,2.632,.087,.045,.190,80.395,-32.821,-19.968,2.924,10.989,9.101,.184,73.542
 4861.000,255.744,192.526,10.465,-23.787,3.910,5.194,8.582,2.640,.075,.041,.179,86.571,-34.759,-20.632,2.912,11.496,10.009,.161,70.285
 4861.500,234.498,167.110,11.149,-24.514,4.264,5.984,8.574,2.641,.066,.040,.163,84.614,-34.966,-21.299,2.894,11.262,9.944,.145,68.077
 4862.000,212.914,147.489,11.175,-25.157,4.697,6.780,8.573,2.638,.060,.042,.153,76.414,-33.425,-21.882,2.865,11.840,10.336,.140,67.251
 4862.500,193.688,132.914,11.600,-25.636,5.163,7.524,8.564,2.629,.056,.047,.150,74.120,-30.961,-22.300,2.852,11.819,10.136,.141,67.498
 4863.000,174.878,122.659,11.944,-25.888,5.718,8.153,8.556,2.612,.052,.058,.151,75.586,-27.479,-22.491,2.842,10.505,9.616,.147,68.237
 4863.500,162.485,117.008,11.724,-25.872,6.154,8.546,8.565,2.588,.048,.071,.152,77.491,-24.460,-22.416,2.835,12.466,10.056,.153,69.213
 4864.000,156.729,115.828,11.667,-25.589,6.380,8.634,8.576,2.568,.046,.083,.154,81.694,-22.252,-22.072,2.859,13.886,10.447,.162,70.376
 4864.500,152.926,117.534,11.392,-25.084,6.539,8.508,8.583,2.562,.050,.086,.156,86.062,-20.131,-21.507,2.891,12.518,9.688,.168,71.323
 4865.000,148.015,119.026,9.883,-24.453,6.756,8.401,8.560,2.576,.059,.078,.156,89.637,-18.276,-20.815,2.918,10.144,8.396,.170,71.519
 4865.500,143.139,117.110,8.692,-23.812,6.986,8.539,8.553,2.603,.068,.062,.155,83.020,-18.371,-20.114,2.868,13.391,10.215,.164,70.640
 4866.000,137.747,111.018,10.941,-23.267,7.260,9.008,8.553,2.630,.070,.047,.143,79.124,-20.894,-19.508,2.853,17.573,12.785,.147,68.299
 4866.500,131.253,102.913,13.490,-22.873,7.619,9.717,8.546,2.650,.066,.035,.121,78.525,-24.699,-19.054,2.841,22.271,15.691,.124,65.027
 4867.000,125.798,95.513,17.305,-22.632,7.949,10.470,8.547,2.666,.062,.026,.102,68.550,-28.826,-18.753,2.812,29.352,20.083,.103,62.087
 4867.500,118.906,89.468,21.223,-22.496,8.410,11.177,8.559,2.682,.061,.016,.087,58.962,-31.565,-18.556,2.802,24.358,15.980,.087,59.787
 4868.000,108.986,83.758,18.216,-22.394,9.175,11.939,8.564,2.699,.062,.006,.076,62.209,-31.976,-18.394,2.803,26.864,18.321,.075,58.163
 4868.500,101.992,78.363,23.352,-22.257,9.805,12.761,8.564,2.711,.060,-.001,.069,61.329,-31.652,-18.196,2.805,36.259,27.474,.071,57.537
 4869.000,98.528,75.456,29.706,-22.034,10.149,13.253,8.565,2.714,.058,-.002,.067,52.580,-30.116,-17.914,2.799,29.820,24.035,.075,58.061
 4869.500,97.179,77.287,22.863,-21.715,10.290,12.939,8.592,2.706,.054,.002,.067,52.738,-26.200,-17.534,2.793,20.063,16.066,.087,59.807
 4870.000,98.780,83.336,14.880,-21.330,10.123,12.000,8.632,2.689,.051,.012,.070,58.349,-20.565,-17.089,2.786,14.840,11.358,.104,62.257
 4870.500,103.107,91.062,11.567,-20.938,9.699,10.981,8.630,2.671,.047,.023,.078,68.039,-14.657,-16.636,2.783,12.686,9.362,.119,64.343
 4871.000,106.683,98.769,10.148,-20.598,9.373,10.125,8.638,2.655,.044,.032,.088,75.850,-9.299,-16.236,2.803,10.934,8.096,.127,65.534
 4871.500,111.763,105.736,9.842,-20.345,8.948,9.458,8.640,2.643,.041,.039,.099,72.158,-6.705,-15.923,2.794,10.814,7.925,.131,66.084
 4872.000,119.635,111.831,9.577,-20.174,8.359,8.942,8.658,2.630,.038,.047,.109,70.317,-6.990,-15.691,2.796,10.944,7.835,.135,66.546
 4872.500,129.654,118.057,9.986,-20.053,7.713,8.470,8.714,2.616,.036,.055,.119,76.361,-8.525,-15.510,2.813,12.072,8.458,.141,67.468
 4873.000,144.105,126.198,10.100,-19.942,6.939,7.924,8.730,2.602,.038,.063,.129,83.258,-10.505,-15.339,2.870,12.027,8.797,.153,69.218
 4873.500,164.389,138.894,8.770,-19.812,6.083,7.200,8.728,2.593,.045,.068,.140,84.051,-12.203,-15.148,2.876,10.519,7.796,.172,71.838
 4874.000,184.726,158.808,7.210,-19.649,5.413,6.297,8.743,2.590,.054,.070,.152,87.188,-12.057,-14.925,2.899,7.783,5.852,.194,75.007
 4874.500,205.035,185.240,5.760,-19.462,4.877,5.398,8.767,2.591,.062,.070,.168,92.680,-10.978,-14.677,2.941,5.827,4.444,.217,78.182
 4875.000,228.318,213.457,5.155,-19.269,4.380,4.685,8.767,2.591,.066,.070,.194,90.372,-10.667,-14.424,2.923,5.600,4.194,.236,80.854
 4875.500,253.874,239.426,5.109,-19.095,3.939,4.177,8.754,2.591,.068,.069,.225,90.152,-11.589,-14.190,2.942,5.786,4.340,.250,82.855
 4876.000,282.277,263.276,5.002,-18.962,3.543,3.798,8.758,2.593,.072,.068,.243,94.153,-13.658,-13.997,2.975,5.712,4.281,.261,84.409
 4876.500,316.065,286.637,4.815,-18.887,3.164,3.489,8.758,2.593,.077,.069,.251,93.937,-16.628,-13.861,2.989,5.435,4.009,.270,85.763
 4877.000,348.681,308.868,4.675,-18.877,2.868,3.238,8.758,2.583,.080,.074,.253,88.716,-19.242,-13.791,2.973,5.115,3.694,.279,86.966
 4877.500,375.549,326.740,4.559,-18.933,2.663,3.060,8.766,2.566,.080,.084,.256,90.530,-20.972,-13.786,2.967,5.134,3.618,.286,88.018
 4878.000,399.678,338.938,4.421,-19.047,2.502,2.950,8.781,2.552,.083,.093,.265,94.543,-22.257,-13.840,2.974,4.939,3.578,.292,88.884
 4878.500,420.890,348.998,4.270,-19.201,2.376,2.865,8.873,2.549,.091,.094,.278,94.573,-23.209,-13.934,2.989,4.384,3.463,.296,89.428
 4879.000,436.682,359.492,4.137,-19.366,2.290,2.782,8.820,2.555,.104,.091,.286,98.304,-23.804,-14.039,3.157,3.976,3.540,.297,89.573
 4879.500,448.887,368.273,4.049,-19.509,2.228,2.715,8.763,2.564,.118,.086,.292,93.888,-24.469,-14.122,3.038,4.202,3.675,.294,89.154
 4880.000,459.926,372.343,4.048,-19.605,2.174,2.686,8.770,2.570,.126,.082,.303,88.654,-25.612,-14.157,3.066,4.291,3.718,.286,88.016
 4880.500,468.413,370.877,4.140,-19.649,2.135,2.696,8.754,2.574,.125,.080,.309,87.762,-27.127,-14.140,3.101,4.306,3.697,.276,86.553
 4881.000,470.954,365.473,4.406,-19.661,2.123,2.736,8.750,2.575,.116,.079,.302,83.583,-28.496,-14.092,3.044,4.594,3.891,.268,85.404
 4881.500,471.187,359.118,4.672,-19.675,2.122,2.785,8.762,2.580,.107,.076,.288,82.254,-29.620,-14.046,3.010,5.158,4.245,.264,84.910
 4882.000,469.475,354.094,4.755,-19.723,2.130,2.824,8.761,2.588,.101,.071,.276,79.937,-30.196,-14.034,2.990,5.873,4.594,.266,85.112
 4882.500,463.616,351.264,4.732,-19.823,2.157,2.847,8.737,2.597,.098,.066,.267,77.428,-29.958,-14.073,2.977,5.248,4.228,.270,85.725
 4883.000,457.807,351.400,4.573,-19.979,2.184,2.846,8.673,2.601,.097,.064,.263,78.467,-29.417,-14.169,2.977,4.847,3.888,.275,86.473
 4883.500,450.470,354.610,4.574,-20.188,2.220,2.820,8.654,2.604,.096,.062,.265,86.026,-28.685,-14.317,2.995,4.984,3.811,.280,87.156
 4884.000,442.663,357.431,4.630,-20.441,2.259,2.798,8.679,2.608,.100,.060,.268,88.537,-28.036,-14.510,3.006,4.698,3.733,.282,87.366
 4884.500,434.664,355.460,4.617,-20.736,2.301,2.813,8.639,2.613,.106,.057,.263,87.247,-27.631,-14.745,3.002,4.527,3.748,.277,86.697
 4885.000,422.964,347.588,4.585,-21.088,2.364,2.877,8.622,2.614,.111,.056,.253,88.926,-27.347,-15.036,3.024,4.823,3.895,.265,84.989
 4885.500,407.466,333.501,4.727,-21.537,2.454,2.999,8.565,2.608,.111,.060,.242,91.043,-27.488,-15.425,2.990,5.596,4.347,.248,82.576
 4886.000,386.988,313.456,5.124,-22.153,2.584,3.190,8.538,2.599,.105,.065,.232,88.213,-28.418,-15.981,2.961,6.886,4.894,.228,79.771
 4886.500,358.055,288.295,5.214,-23.017,2.793,3.469,8.493,2.595,.099,.067,.221,85.104,-30.134,-16.784,2.936,7.362,5.271,.206,76.660
 4887.000,327.674,257.671,5.648,-24.201,3.052,3.881,8.426,2.602,.094,.063,.204,90.112,-32.831,-17.908,2.927,12.730,8.734,.186,73.812
 4887.500,302.256,225.814,8.689,-25.763,3.309,4.428,8.394,2.612,.087,.057,.188,86.421,-35.637,-19.410,2.907,19.554,13.100,.172,71.787
 4888.000,278.206,200.569,11.673,-27.757,3.595,4.986,8.386,2.622,.079,.052,.171,78.850,-36.339,-21.343,2.880,17.852,12.308,.165,70.836
 4888.500,256.707,184.160,10.833,-30.246,3.895,5.430,8.376,2.629,.073,.048,.153,77.982,-34.287,-23.772,2.860,13.448,9.790,.166,71.050
 4889.000,239.327,173.158,8.787,-33.309,4.178,5.775,8.372,2.631,.072,.046,.140,82.932,-30.266,-26.774,2.868,10.757,8.333,.172,71.865
 4889.500,222.547,164.626,7.718,-37.005,4.493,6.074,8.358,2.625,.073,.049,.138,90.160,-25.084,-30.410,2.922,10.970,8.726,.177,72.510
 4890.000,211.532,159.355,7.918,-41.334,4.727,6.275,8.330,2.612,.074,.057,.145,91.512,-20.890,-34.679,2.892,12.184,9.514,.180,72.902
 4890.500,211.311,159.868,7.909,-46.217,4.732,6.255,8.281,2.593,.073,.068,.154,79.964,-19.194,-39.501,2.850,12.686,9.674,.184,73.497
 4891.000,217.949,166.589,7.380,-51.501,4.588,6.003,8.283,2.569,.071,.083,.158,74.196,-19.279,-44.725,2.824,13.699,10.296,.190,74.414
 4891.500,227.918,176.895,6.956,-56.995,4.387,5.653,8.249,2.539,.067,.100,.155,72.312,-20.595,-50.158,2.801,12.774,10.252,.196,75.272
 4892.000,237.754,187.536,7.028,-62.492,4.206,5.332,8.206,2.510,.065,.117,.150,69.603,-22.829,-55.596,2.775,9.173,8.840,.200,75.833
 4892.500,246.425,197.090,7.568,-67.785,4.058,5.074,8.129,2.487,.067,.131,.153,66.254,-25.830,-60.828,2.761,6.510,7.570,.202,76.146
 4893.000,256.617,205.512,8.338,-72.666,3.897,4.866,8.100,2.475,.071,.138,.159,69.902,-29.491,-65.648,2.769,5.549,7.000,.204,76.372
 4893.500,268.378,213.135,9.120,-76.954,3.726,4.692,8.075,2.474,.077,.138,.156,67.631,-33.001,-69.876,2.759,5.196,6.748,.206,76.673
 4894.000,280.156,220.780,9.584,-80.532,3.569,4.529,8.075,2.480,.081,.134,.151,59.096,-35.514,-73.394,2.747,5.082,6.670,.209,77.056
 4894.500,291.203,228.795,9.219,-83.378,3.434,4.371,8.078,2.483,.082,.133,.156,58.278,-36.819,-76.179,2.752,5.194,6.753,.211,77.375
 4895.000,299.311,236.013,8.339,-85.561,3.341,4.237,8.068,2.479,.081,.135,.167,64.945,-37.070,-78.302,2.762,5.352,6.856,.212,77.533
 4895.500,304.282,240.924,7.950,-87.211,3.286,4.151,8.042,2.474,.081,.138,.171,69.517,-36.936,-79.892,2.760,5.227,6.762,.212,77.549
 4896.000,308.696,243.678,8.243,-88.475,3.239,4.104,8.011,2.474,.083,.138,.168,67.865,-37.148,-81.096,2.755,5.094,6.703,.212,77.477
 4896.500,314.351,245.887,8.628,-89.484,3.181,4.067,8.003,2.479,.088,.135,.163,65.778,-37.813,-82.045,2.752,5.235,6.848,.211,77.400
 4897.000,320.531,248.544,8.554,-90.334,3.120,4.023,8.003,2.486,.092,.131,.160,65.354,-38.546,-82.834,2.752,5.326,6.870,.211,77.346
 4897.500,326.717,251.251,8.142,-91.075,3.061,3.980,7.982,2.490,.095,.129,.164,67.423,-39.227,-83.515,2.758,5.051,6.609,.211,77.286
 4898.000,332.457,253.497,8.133,-91.708,3.008,3.945,7.968,2.488,.095,.130,.179,76.853,-39.977,-84.087,2.771,4.891,6.499,.210,77.194
 4898.500,336.324,255.544,8.441,-92.191,2.973,3.913,7.967,2.484,.095,.132,.196,84.981,-40.760,-84.510,2.786,4.870,6.503,.209,77.068
 4899.000,338.988,257.581,8.539,-92.460,2.950,3.882,7.967,2.483,.095,.133,.208,80.630,-41.607,-84.719,2.798,4.847,6.515,.208,76.949
 4899.500,340.953,259.064,8.673,-92.451,2.933,3.860,7.966,2.486,.097,.131,.211,70.480,-42.454,-84.650,2.803,4.862,6.560,.207,76.808
 4900.000,341.564,259.448,8.913,-92.108,2.928,3.854,7.966,2.488,.098,.130,.208,71.549,-43.167,-84.246,2.801,4.819,6.487,.205,76.531
 4900.500,340.967,258.650,8.921,-91.373,2.933,3.866,7.966,2.487,.098,.130,.194,69.925,-43.809,-83.451,2.787,4.781,6.431,.202,76.090
 4901.000,338.723,256.668,8.947,-90.178,2.952,3.896,7.969,2.487,.095,.131,.171,68.502,-44.397,-82.195,2.764,4.816,6.493,.199,75.593
 4901.500,334.276,253.664,9.375,-88.438,2.991,3.942,7.968,2.488,.092,.130,.154,71.188,-44.769,-80.395,2.751,4.852,6.567,.196,75.188
 4902.000,329.339,250.375,9.972,-86.074,3.036,3.994,7.970,2.490,.087,.128,.151,73.082,-44.769,-77.970,2.753,4.905,6.660,.194,74.973
 4902.500,324.591,247.784,10.193,-83.039,3.081,4.036,7.995,2.494,.084,.126,.154,73.346,-44.066,-74.875,2.761,5.154,6.927,.194,74.969
 4903.000,318.914,246.130,9.596,-79.341,3.136,4.063,8.011,2.498,.082,.124,.152,68.352,-42.395,-71.117,2.765,5.790,7.464,.195,75.128
 4903.500,312.078,244.273,8.593,-75.051,3.204,4.094,8.021,2.500,.079,.123,.146,66.863,-39.996,-66.767,2.761,6.132,7.756,.197,75.306
 4904.000,303.822,240.669,8.233,-70.288,3.291,4.155,8.016,2.504,.077,.121,.141,72.657,-37.244,-61.944,2.769,6.454,8.059,.197,75.305
 4904.500,293.671,234.924,8.398,-65.212,3.405,4.257,8.019,2.512,.075,.116,.136,75.139,-34.222,-56.807,2.775,8.340,8.896,.195,75.049
 4905.000,284.043,227.535,8.139,-60.012,3.521,4.395,8.019,2.521,.072,.110,.133,79.114,-31.164,-51.547,2.786,11.134,9.193,.192,74.610
 4905.500,274.294,218.649,7.202,-54.892,3.646,4.574,8.019,2.526,.067,.108,.134,88.686,-28.119,-46.366,2.815,11.442,8.527,.188,74.103
 4906.000,263.238,208.301,6.614,-50.043,3.799,4.801,8.018,2.528,.062,.106,.138,91.304,-25.434,-41.457,2.847,10.553,8.061,.185,73.611
 4906.500,252.025,197.259,6.826,-45.612,3.968,5.069,8.010,2.534,.060,.103,.144,84.516,-23.713,-36.966,2.877,10.365,8.142,.182,73.212
 4907.000,241.367,186.946,7.427,-41.678,4.143,5.349,8.014,2.543,.060,.097,.150,78.010,-22.884,-32.971,2.815,10.580,8.324,.181,73.051
 4907.500,231.119,179.044,8.033,-38.256,4.327,5.585,8.020,2.554,.060,.091,.157,78.269,-22.411,-29.489,2.826,10.413,8.284,.182,73.276
 4908.000,222.124,174.601,8.226,-35.334,4.502,5.727,8.013,2.565,.061,.085,.162,86.409,-22.880,-26.506,2.893,9.769,7.814,.184,73.603
 4908.500,212.321,172.715,7.604,-32.906,4.710,5.790,8.010,2.578,.062,.077,.156,96.963,-26.758,-24.018,2.969,8.657,6.970,.181,73.087
 4909.000,198.899,170.056,6.705,-30.985,5.028,5.880,8.016,2.594,.063,.068,.136,103.015,-37.105,-22.037,2.984,10.205,7.966,.164,70.719
 4909.500,182.151,161.930,7.733,-29.592,5.490,6.175,7.985,2.613,.063,.057,.111,89.202,-52.762,-20.583,2.914,26.123,17.784,.133,66.387
 4910.000,163.554,145.241,20.274,-28.715,6.114,6.885,7.964,2.633,.062,.045,.085,64.558,-68.847,-19.646,2.766,54.295,36.374,.096,61.130
 4910.500,145.228,121.817,52.431,-28.290,6.886,8.209,7.965,2.651,.060,.034,.062,39.609,-82.267,-19.161,2.743,57.077,42.174,.063,56.465
 4911.000,129.680,97.174,75.701,-28.195,7.711,10.291,7.968,2.663,.057,.027,.049,25.690,-92.639,-19.006,2.736,57.946,49.859,.043,53.532
 4911.500,114.158,75.209,106.008,-28.275,8.760,13.296,7.965,2.665,.055,.026,.044,21.806,-99.044,-19.025,2.731,64.687,59.246,.034,52.330
 4912.000,95.842,56.646,153.795,-28.379,10.434,17.653,7.966,2.659,.052,.030,.041,20.465,-99.971,-19.069,2.724,64.194,58.307,.032,52.040
 4912.500,78.411,41.678,183.268,-28.392,12.753,23.993,7.967,2.653,.051,.033,.041,22.977,-95.787,-19.022,2.719,61.331,53.888,.035,52.386
 4913.000,66.175,31.450,185.730,-28.250,15.111,31.796,7.962,2.653,.052,.033,.041,23.875,-88.142,-18.819,2.720,65.213,53.480,.047,54.152
 4913.500,61.338,27.888,151.059,-27.938,16.303,35.858,7.961,2.652,.055,.034,.045,25.628,-78.969,-18.447,2.724,56.899,44.586,.078,58.521
 4914.000,64.439,32.478,83.086,-27.489,15.519,30.790,7.959,2.644,.056,.039,.054,33.215,-69.226,-17.937,2.728,33.653,25.370,.125,65.185
 4914.500,71.312,44.838,30.923,-26.971,14.023,22.302,7.965,2.626,.056,.049,.067,50.280,-56.519,-17.359,2.735,16.402,13.173,.166,71.014
 4915.000,78.307,61.380,11.958,-26.472,12.770,16.292,7.971,2.610,.055,.058,.083,70.343,-41.227,-16.800,2.757,12.562,10.429,.176,72.400
 4915.500,83.569,75.823,9.853,-26.081,11.966,13.189,7.974,2.609,.056,.059,.096,77.998,-29.858,-16.349,2.810,25.095,19.710,.152,69.026
 4916.000,86.808,83.530,15.909,-25.861,11.520,11.972,7.970,2.627,.059,.049,.100,72.129,-29.636,-16.067,2.786,49.039,41.029,.118,64.168
 4916.500,89.074,84.501,29.943,-25.833,11.227,11.834,7.970,2.657,.063,.031,.091,49.366,-37.006,-15.980,2.783,47.104,43.654,.097,61.281
 4917.000,90.276,81.339,40.942,-25.984,11.077,12.294,7.963,2.685,.064,.015,.076,37.012,-44.122,-16.070,2.780,41.726,40.350,.097,61.202
 4917.500,88.671,75.962,45.355,-26.276,11.278,13.165,7.971,2.696,.061,.008,.063,39.276,-46.900,-16.301,2.775,38.352,37.814,.103,62.060
 4918.000,82.590,69.002,43.154,-26.660,12.108,14.492,7.978,2.690,.055,.012,.055,38.546,-44.065,-16.626,2.762,31.587,33.007,.099,61.456
 4918.500,74.700,61.250,34.999,-27.093,13.387,16.326,7.971,2.676,.048,.020,.049,37.507,-37.244,-16.998,2.746,25.939,27.893,.082,59.064
 4919.000,67.989,54.115,28.545,-27.533,14.708,18.479,7.979,2.664,.044,.027,.046,40.089,-28.953,-17.378,2.735,21.286,25.207,.065,56.712
 4919.500,63.712,49.065,26.234,-27.943,15.696,20.381,7.977,2.658,.041,.031,.046,39.743,-21.114,-17.727,2.730,23.612,27.854,.058,55.712
 4920.000,63.313,47.315,23.555,-28.290,15.795,21.135,7.972,2.656,.041,.032,.050,42.380,-15.399,-18.014,2.733,26.411,27.279,.059,55.862
 4920.500,66.188,49.320,19.880,-28.547,15.108,20.276,7.974,2.659,.045,.030,.055,47.417,-11.610,-18.211,2.742,24.137,23.426,.065,56.678
 4921.000,70.705,54.414,16.489,-28.695,14.143,18.378,7.971,2.665,.053,.026,.062,43.106,-8.865,-18.299,2.754,21.766,20.934,.073,57.764
 4921.500,76.779,61.199,13.884,-28.727,13.024,16.340,7.972,2.672,.062,.022,.068,41.794,-7.580,-18.270,2.764,22.104,21.077,.079,58.743
 4922.000,83.261,68.537,13.542,-28.644,12.010,14.591,7.977,2.675,.069,.020,.071,47.539,-7.571,-18.127,2.773,22.838,21.024,.084,59.391
 4922.500,90.177,76.098,14.047,-28.453,11.089,13.141,7.972,2.673,.070,.022,.073,50.406,-8.625,-17.875,2.775,16.824,16.521,.086,59.719
 4923.000,98.317,83.688,13.849,-28.161,10.171,11.949,7.987,2.665,.066,.026,.077,47.229,-10.246,-17.523,2.773,14.660,14.493,.088,59.989
 4923.500,105.183,91.021,13.163,-27.781,9.507,10.986,7.990,2.656,.059,.032,.083,49.154,-10.830,-17.082,2.773,13.009,12.014,.092,60.450
 4924.000,110.287,97.744,11.194,-27.334,9.067,10.231,7.983,2.651,.051,.034,.087,51.965,-10.476,-16.576,2.776,10.000,9.036,.096,61.104
 4924.500,114.530,102.980,10.112,-26.859,8.731,9.711,7.990,2.655,.048,.032,.088,54.575,-10.328,-16.040,2.780,10.097,8.553,.101,61.783
 4925.000,117.819,106.000,10.597,-26.403,8.488,9.434,7.999,2.664,.048,.027,.089,56.139,-10.944,-15.523,2.789,12.235,9.997,.104,62.226
 4925.500,120.482,107.306,11.716,-26.013,8.300,9.319,7.991,2.672,.050,.022,.090,50.606,-12.271,-15.073,2.793,14.529,11.925,.104,62.276
 4926.000,122.675,108.004,11.907,-25.721,8.152,9.259,7.987,2.674,.051,.021,.091,49.228,-13.806,-14.721,2.794,13.530,11.383,.103,62.010
 4926.500,123.769,108.409,11.520,-25.534,8.080,9.224,7.992,2.671,.049,.023,.089,49.674,-15.044,-14.474,2.790,12.808,10.776,.099,61.524
 4927.000,123.478,108.116,11.879,-25.438,8.099,9.249,7.992,2.667,.047,.025,.086,47.194,-15.892,-14.318,2.783,13.960,12.042,.095,60.902
 4927.500,122.414,107.080,12.767,-25.411,8.169,9.339,7.988,2.665,.047,.026,.084,45.463,-16.499,-14.230,2.779,14.422,12.714,.091,60.360
 4928.000,121.236,105.742,13.031,-25.432,8.248,9.457,7.982,2.664,.050,.027,.085,51.662,-16.911,-14.191,2.782,12.777,11.497,.089,60.121
 4928.500,120.623,104.416,12.904,-25.489,8.290,9.577,7.987,2.661,.056,.029,.083,59.695,-17.260,-14.187,2.781,12.642,11.239,.090,60.247
 4929.000,120.553,103.215,12.942,-25.571,8.295,9.689,8.012,2.658,.064,.031,.080,62.817,-17.610,-14.209,2.774,13.568,11.755,.092,60.575
 4929.500,120.528,102.399,13.122,-25.666,8.297,9.766,8.041,2.654,.070,.033,.078,63.096,-17.893,-14.243,2.770,13.225,11.628,.095,60.888
 4930.000,120.662,102.418,13.271,-25.756,8.288,9.764,8.057,2.652,.072,.034,.077,56.815,-18.147,-14.274,2.765,13.267,11.531,.096,61.123
 4930.500,120.782,103.625,13.364,-25.827,8.279,9.650,8.063,2.652,.069,.034,.078,55.867,-18.217,-14.284,2.767,14.244,11.624,.098,61.313
 4931.000,120.700,105.898,13.415,-25.869,8.285,9.443,8.060,2.658,.067,.031,.080,62.510,-17.917,-14.266,2.774,13.699,10.454,.099,61.537
 4931.500,120.865,108.582,12.987,-25.882,8.274,9.210,8.062,2.665,.065,.026,.084,66.666,-17.291,-14.218,2.785,13.250,9.531,.102,61.953
 4932.000,121.103,111.129,12.800,-25.872,8.257,8.999,8.071,2.672,.063,.022,.087,69.839,-16.211,-14.147,2.797,13.689,9.531,.107,62.649
 4932.500,121.406,113.601,12.380,-25.853,8.237,8.803,8.058,2.674,.058,.021,.092,74.979,-14.683,-14.069,2.811,13.759,9.331,.114,63.603
 4933.000,123.475,116.209,11.311,-25.842,8.099,8.605,8.050,2.670,.053,.023,.098,76.130,-13.467,-13.997,2.819,11.678,8.342,.122,64.737
 4933.500,126.710,118.766,10.276,-25.848,7.892,8.420,8.043,2.661,.050,.028,.104,73.166,-12.803,-13.943,2.815,9.827,7.422,.130,65.855
 4934.000,130.355,121.057,10.030,-25.881,7.671,8.261,7.993,2.653,.052,.033,.107,71.048,-12.830,-13.916,2.810,9.143,6.990,.137,66.837
 4934.500,134.947,123.259,10.644,-25.947,7.410,8.113,7.974,2.649,.058,.036,.109,70.170,-13.674,-13.921,2.807,9.175,7.091,.144,67.945
 4935.000,139.703,125.471,11.199,-26.053,7.158,7.970,7.968,2.648,.061,.036,.108,76.052,-14.837,-13.967,2.818,9.072,6.940,.158,69.787
 4935.500,142.912,126.716,9.763,-26.206,6.997,7.892,7.967,2.648,.061,.037,.106,93.101,-15.862,-14.060,2.944,8.249,6.462,.177,72.615
 4936.000,146.949,125.869,9.222,-26.406,6.805,7.945,7.970,2.640,.056,.041,.104,114.734,-17.521,-14.199,3.000,10.039,8.314,.198,75.449
 4936.500,156.227,125.315,11.984,-26.641,6.401,7.980,7.965,2.622,.050,.051,.104,107.592,-20.362,-14.374,3.000,13.934,11.387,.209,77.042
 4937.000,173.104,131.621,12.860,-26.894,5.777,7.598,7.962,2.601,.049,.064,.107,75.897,-23.487,-14.567,2.794,15.174,11.073,.213,77.579
 4937.500,196.305,150.237,10.426,-27.153,5.094,6.656,7.969,2.585,.057,.073,.114,61.158,-25.253,-14.765,2.767,14.160,9.535,.216,78.050
 4938.000,222.193,180.503,8.189,-27.411,4.501,5.540,7.972,2.580,.072,.076,.128,62.894,-24.684,-14.963,2.780,12.069,8.221,.229,79.969
 4938.500,249.815,217.099,6.515,-27.666,4.003,4.606,7.967,2.580,.090,.076,.151,66.991,-22.507,-15.157,2.811,8.738,6.343,.264,84.890
 4939.000,276.757,255.073,5.326,-27.916,3.613,3.920,7.973,2.576,.103,.078,.188,73.838,-19.881,-15.347,2.863,6.466,4.707,.310,91.294
 4939.500,300.000,290.118,4.516,-28.160,3.333,3.447,7.969,2.566,.111,.084,.224,79.949,-18.164,-15.531,2.913,5.191,3.911,.340,95.563
 4940.000,319.659,315.532,4.247,-28.398,3.128,3.169,7.963,2.554,.113,.091,.235,80.312,-18.792,-15.708,2.920,5.699,4.084,.342,95.953
 4940.500,333.413,325.098,4.697,-28.625,2.999,3.076,7.965,2.545,.111,.096,.234,82.258,-21.873,-15.875,2.916,8.484,5.114,.320,92.754
 4941.000,337.836,318.342,5.630,-28.833,2.960,3.141,7.958,2.544,.105,.097,.225,90.226,-26.450,-16.023,2.922,9.216,5.684,.281,87.251
 4941.500,328.790,299.324,6.011,-29.020,3.042,3.341,7.947,2.553,.099,.092,.201,102.157,-31.151,-16.149,3.000,7.808,5.848,.238,81.223
 4942.000,308.056,272.217,7.090,-29.189,3.246,3.674,7.941,2.569,.091,.083,.162,99.988,-35.052,-16.258,3.000,9.594,7.138,.201,75.920
 4942.500,285.564,240.470,9.719,-29.358,3.502,4.159,7.947,2.587,.082,.072,.138,91.149,-37.954,-16.366,2.929,12.382,9.176,.172,71.820
 4943.000,261.712,209.115,11.946,-29.539,3.821,4.782,7.955,2.600,.073,.064,.128,90.571,-38.573,-16.488,2.925,13.562,10.258,.156,69.587
 4943.500,238.917,184.458,12.190,-29.728,4.186,5.421,7.958,2.605,.063,.061,.127,92.309,-36.448,-16.616,2.938,12.918,10.009,.155,69.421
 4944.000,221.202,170.136,11.400,-29.894,4.521,5.878,7.965,2.605,.056,.061,.136,92.695,-32.270,-16.721,2.941,11.466,9.236,.159,70.040
 4944.500,207.253,165.144,9.609,-30.004,4.825,6.055,7.941,2.606,.051,.061,.150,90.037,-26.766,-16.771,2.921,8.240,7.361,.162,70.389
 4945.000,197.333,165.310,7.390,-30.059,5.068,6.049,7.893,2.609,.049,.059,.160,90.948,-21.729,-16.765,2.928,6.246,5.841,.163,70.502
 4945.500,191.160,165.831,7.091,-30.122,5.231,6.030,7.889,2.615,.049,.055,.166,95.465,-19.257,-16.769,2.963,8.035,6.398,.160,70.126
 4946.000,186.404,163.896,8.292,-30.317,5.365,6.101,7.890,2.623,.050,.051,.162,89.285,-20.965,-16.903,2.915,10.082,7.432,.151,68.808
 4946.500,180.865,158.942,9.141,-30.781,5.529,6.292,7.889,2.631,.052,.046,.146,79.494,-28.991,-17.307,2.858,10.808,8.178,.135,66.616
 4947.000,173.096,150.052,9.436,-31.613,5.777,6.664,7.890,2.637,.052,.042,.125,69.323,-44.947,-18.078,2.821,11.749,9.062,.114,63.654
 4947.500,158.717,135.033,10.917,-32.835,6.300,7.406,7.867,2.637,.047,.043,.105,56.140,-64.687,-19.240,2.788,16.829,11.517,.089,60.084
 4948.000,139.364,113.480,23.374,-34.389,7.175,8.812,7.801,2.625,.039,.050,.086,45.598,-82.186,-20.734,2.754,37.353,19.787,.065,56.752
 4948.500,120.604,89.303,79.957,-36.148,8.292,11.198,7.795,2.600,.035,.065,.075,36.432,-94.644,-22.433,2.722,63.117,31.233,.051,54.753
 4949.000,100.205,67.752,170.025,-37.950,9.980,14.760,7.795,2.572,.038,.081,.072,33.713,-99.791,-24.174,2.703,64.273,34.211,.050,54.575
 4949.500,81.377,50.835,195.872,-39.627,12.288,19.671,7.797,2.553,.047,.092,.076,34.016,-98.726,-25.791,2.697,48.692,28.497,.058,55.706
 4950.000,65.805,37.547,171.478,-41.039,15.196,26.633,7.795,2.545,.057,.096,.079,29.480,-93.530,-27.142,2.695,28.925,22.492,.067,56.923
 4950.500,51.461,27.140,161.217,-42.098,19.432,36.846,7.795,2.550,.061,.094,.076,24.520,-84.762,-28.141,2.694,33.749,29.726,.069,57.224
 4951.000,39.973,19.736,171.872,-42.779,25.017,50.669,7.796,2.566,.060,.084,.067,22.508,-74.714,-28.762,2.695,58.451,44.880,.063,56.414
 4951.500,33.390,15.238,180.565,-43.113,29.949,65.627,7.798,2.594,.058,.068,.057,25.934,-66.926,-29.035,2.700,73.371,53.862,.052,54.879
 4952.000,29.758,13.044,167.440,-43.159,33.605,76.664,7.797,2.629,.057,.047,.046,30.592,-61.333,-29.021,2.709,65.930,48.638,.040,53.213
 4952.500,27.600,12.219,135.638,-42.982,36.231,81.837,7.801,2.661,.057,.029,.038,32.458,-57.747,-28.784,2.721,53.974,40.087,.031,51.887
 4953.000,26.334,11.909,133.903,-42.635,37.973,83.967,7.801,2.679,.056,.018,.031,33.572,-56.603,-28.376,2.726,64.101,44.462,.025,50.978
 4953.500,25.048,11.657,177.624,-42.149,39.923,85.783,7.811,2.685,.054,.014,.026,30.446,-56.472,-27.830,2.725,79.607,52.586,.021,50.407
 4954.000,23.452,11.347,200.476,-41.539,42.641,88.126,7.818,2.686,.053,.014,.023,27.772,-55.643,-27.160,2.722,82.830,54.946,.019,50.179
 4954.500,22.005,10.990,188.182,-40.809,45.443,90.996,7.812,2.688,.052,.013,.021,27.344,-53.798,-26.370,2.721,80.452,54.473,.019,50.203
 4955.000,20.962,10.648,178.335,-39.963,47.705,93.914,7.802,2.691,.052,.011,.021,30.739,-51.119,-25.463,2.723,81.329,54.239,.020,50.308
 4955.500,20.285,10.509,178.757,-39.011,49.299,95.158,7.817,2.696,.053,.008,.021,34.583,-47.567,-24.450,2.727,82.849,54.366,.021,50.465
 4956.000,20.436,10.924,164.746,-37.976,48.933,91.540,7.813,2.703,.054,.004,.021,33.809,-43.840,-23.356,2.732,81.654,53.550,.023,50.773
 4956.500,21.360,12.333,138.924,-36.900,46.817,81.086,7.803,2.708,.056,.001,.023,39.212,-39.456,-22.219,2.738,77.220,49.658,.027,51.296
 4957.000,22.736,14.984,95.667,-35.835,43.984,66.739,7.821,2.706,.055,.002,.026,47.525,-33.830,-21.094,2.740,62.905,39.740,.032,52.086
 4957.500,24.795,18.651,67.792,-34.837,40.330,53.616,7.831,2.697,.054,.008,.030,52.526,-28.702,-20.035,2.739,53.890,35.067,.039,53.040
 4958.000,26.442,22.559,53.323,-33.953,37.818,44.328,7.819,2.687,.054,.013,.033,65.853,-26.110,-19.091,2.740,44.131,30.906,.043,53.639
 4958.500,26.603,25.384,35.252,-33.214,37.590,39.396,7.829,2.680,.054,.017,.034,88.830,-29.014,-18.291,2.911,42.295,28.386,.042,53.426
 4959.000,26.278,25.808,59.756,-32.625,38.054,38.748,7.832,2.676,.054,.020,.032,84.530,-37.598,-17.642,2.879,66.711,40.416,.035,52.498
 4959.500,26.694,23.995,152.997,-32.165,37.461,41.675,7.828,2.669,.052,.024,.029,61.382,-47.540,-17.122,2.724,84.148,53.833,.027,51.363
 4960.000,28.061,21.917,209.286,-31.794,35.637,45.626,7.831,2.660,.048,.029,.027,46.505,-54.607,-16.690,2.712,90.271,62.698,.024,50.868
 4960.500,30.683,21.683,191.580,-31.460,32.591,46.119,7.829,2.649,.043,.036,.027,41.838,-57.244,-16.296,2.705,97.675,67.755,.029,51.648
 4961.000,34.006,24.110,134.264,-31.115,29.407,41.477,7.823,2.643,.040,.039,.031,40.220,-54.122,-15.891,2.704,85.043,58.646,.042,53.444
 4961.500,36.691,28.765,58.474,-30.733,27.255,34.764,7.824,2.646,.042,.038,.036,46.591,-44.205,-15.449,2.714,50.176,34.125,.057,55.497
 4962.000,38.973,34.713,24.385,-30.311,25.659,28.808,7.840,2.659,.048,.030,.044,58.697,-29.630,-14.966,2.734,29.617,19.530,.069,57.204
 4962.500,42.112,40.939,20.200,-29.867,23.746,24.427,7.827,2.677,.055,.019,.051,63.699,-15.304,-14.462,2.755,26.044,17.253,.076,58.261
 4963.000,47.093,46.715,20.149,-29.429,21.235,21.406,7.836,2.690,.061,.012,.057,57.181,-6.646,-13.963,2.769,23.940,16.164,.079,58.701
 4963.500,54.215,52.016,20.134,-29.019,18.445,19.225,7.839,2.691,.063,.011,.060,53.674,-5.300,-13.493,2.774,23.060,15.331,.080,58.798
 4964.000,60.793,56.965,19.528,-28.652,16.449,17.555,7.801,2.684,.062,.015,.062,52.262,-6.869,-13.066,2.770,22.394,13.959,.080,58.829
 4964.500,65.833,61.193,18.575,-28.339,15.190,16.342,7.788,2.672,.060,.022,.062,45.273,-8.487,-12.693,2.760,22.895,14.057,.081,58.956
 4965.000,69.558,64.402,18.340,-28.085,14.377,15.527,7.789,2.659,.060,.030,.063,44.908,-9.473,-12.379,2.751,23.699,15.595,.083,59.185
 4965.500,72.062,66.850,17.973,-27.888,13.877,14.959,7.789,2.646,.062,.038,.066,50.655,-9.773,-12.121,2.746,21.727,14.452,.084,59.436
 4966.000,73.833,68.811,17.125,-27.734,13.544,14.533,7.788,2.636,.069,.043,.069,49.898,-9.781,-11.907,2.743,16.469,11.747,.086,59.688
 4966.500,75.338,70.155,16.529,-27.611,13.274,14.254,7.788,2.636,.079,.043,.072,51.721,-9.974,-11.723,2.746,14.111,11.307,.088,59.949
 4967.000,76.456,70.715,16.561,-27.512,13.079,14.141,7.787,2.645,.091,.038,.073,57.824,-10.483,-11.564,2.756,14.393,11.910,.089,60.152
 4967.500,77.190,70.642,17.164,-27.446,12.955,14.156,7.785,2.661,.101,.029,.072,59.850,-11.354,-11.437,2.766,19.055,14.782,.090,60.266
 4968.000,77.626,70.217,17.615,-27.428,12.882,14.241,7.785,2.677,.106,.019,.070,61.297,-12.551,-11.359,2.776,28.393,19.730,.090,60.255
 4968.500,77.855,69.528,17.883,-27.472,12.844,14.383,7.787,2.689,.107,.012,.068,64.422,-14.028,-11.343,2.783,34.638,21.621,.089,60.030
 4969.000,77.846,68.579,18.881,-27.584,12.846,14.582,7.792,2.690,.103,.012,.068,72.394,-15.614,-11.395,2.788,30.074,18.562,.086,59.663
 4969.500,77.798,67.669,20.050,-27.759,12.854,14.778,7.791,2.680,.097,.018,.069,84.671,-17.023,-11.509,2.880,23.923,15.966,.085,59.476
 4970.000,78.039,67.423,21.978,-27.981,12.814,14.832,7.791,2.665,.089,.026,.069,90.748,-17.831,-11.670,2.926,25.262,16.952,.087,59.874
 4970.500,78.720,68.352,22.049,-28.229,12.703,14.630,7.792,2.651,.080,.034,.071,95.190,-17.669,-11.858,2.961,28.299,18.157,.095,60.943
 4971.000,79.311,70.337,19.192,-28.478,12.609,14.217,7.792,2.640,.069,.041,.075,89.222,-16.385,-12.047,2.914,25.882,16.716,.104,62.257
 4971.500,79.565,72.489,16.771,-28.711,12.568,13.795,7.795,2.633,.059,.045,.081,86.473,-14.620,-12.219,2.894,21.264,13.944,.111,63.201
 4972.000,79.862,73.772,16.320,-28.923,12.521,13.555,7.795,2.634,.051,.044,.087,75.906,-13.505,-12.371,2.794,20.874,13.283,.113,63.465
 4972.500,80.539,73.914,17.301,-29.128,12.416,13.529,7.792,2.641,.048,.040,.090,66.369,-13.640,-12.516,2.777,21.779,13.807,.111,63.198
 4973.000,81.356,73.395,17.856,-29.353,12.292,13.625,7.791,2.646,.045,.037,.085,55.339,-14.684,-12.680,2.772,21.799,13.911,.108,62.771
 4973.500,81.694,72.624,18.072,-29.619,12.241,13.769,7.791,2.644,.043,.038,.080,54.194,-15.923,-12.887,2.763,21.772,14.049,.105,62.401
 4974.000,81.139,71.590,19.430,-29.944,12.325,13.968,7.790,2.642,.043,.040,.078,57.741,-17.047,-13.151,2.759,22.390,14.480,.103,62.063
 4974.500,80.082,70.156,19.482,-30.336,12.487,14.254,7.792,2.646,.048,.037,.078,55.135,-18.636,-13.482,2.763,22.159,14.452,.100,61.621
 4975.000,78.704,68.253,18.397,-30.804,12.706,14.651,7.791,2.653,.054,.034,.078,51.921,-21.251,-13.890,2.766,21.231,14.203,.097,61.157
 4975.500,77.779,66.144,21.065,-31.369,12.857,15.119,7.789,2.644,.057,.038,.079,45.259,-24.770,-14.395,2.759,25.691,17.441,.101,61.839
 4976.000,79.002,65.050,32.281,-32.070,12.658,15.373,7.783,2.600,.054,.064,.089,44.905,-28.336,-15.035,2.740,38.623,25.627,.129,65.781
 4976.500,81.443,66.619,36.778,-32.979,12.279,15.011,7.784,2.519,.048,.112,.109,72.078,-29.944,-15.884,2.747,41.842,26.421,.186,73.847
 4977.000,83.011,70.619,22.299,-34.206,12.047,14.160,7.777,2.426,.046,.166,.141,156.665,-28.715,-17.051,3.000,26.034,15.264,.260,84.330
 4977.500,83.764,74.696,15.680,-35.889,11.938,13.388,7.777,2.355,.052,.208,.201,257.318,-26.806,-18.673,3.000,22.700,11.594,.326,93.650
 4978.000,84.403,77.578,22.895,-38.159,11.848,12.890,7.776,2.325,.061,.225,.254,322.980,-27.513,-20.883,2.993,31.631,16.780,.354,97.555
 4978.500,83.156,79.711,25.644,-41.094,12.026,12.545,7.774,2.342,.069,.215,.264,346.328,-32.144,-23.758,2.973,30.398,16.995,.326,93.698
 4979.000,79.745,79.815,18.425,-44.665,12.540,12.529,7.753,2.399,.073,.182,.231,275.274,-40.407,-27.268,2.945,28.398,19.969,.258,84.037
 4979.500,75.774,75.204,29.619,-48.700,13.197,13.297,7.722,2.473,.074,.139,.165,141.594,-49.856,-31.243,2.917,32.455,27.774,.180,73.036
 4980.000,72.253,66.652,79.733,-52.874,13.840,15.003,7.685,2.534,.071,.103,.122,56.104,-56.810,-35.357,2.744,20.051,19.233,.120,64.480
 4980.500,70.236,58.819,104.035,-56.741,14.238,17.001,7.683,2.562,.069,.086,.099,25.269,-59.270,-39.163,2.723,9.598,10.943,.091,60.327
 4981.000,69.884,55.030,71.244,-59.796,14.309,18.172,7.686,2.561,.069,.087,.088,24.685,-56.946,-42.158,2.711,7.727,9.362,.087,59.870
 4981.500,68.289,54.333,39.969,-61.579,14.644,18.405,7.686,2.552,.072,.093,.086,26.083,-50.003,-43.881,2.705,7.545,9.245,.092,60.505
 4982.000,64.569,53.942,28.014,-61.773,15.487,18.538,7.694,2.556,.076,.090,.085,29.125,-42.030,-44.015,2.705,7.574,9.459,.090,60.282
 4982.500,61.652,52.409,27.551,-60.287,16.220,19.081,7.734,2.581,.082,.075,.078,33.728,-38.952,-42.468,2.713,8.770,11.006,.081,58.999
 4983.000,63.214,50.426,45.526,-57.288,15.819,19.831,7.787,2.620,.086,.052,.067,33.234,-42.437,-39.409,2.727,17.115,19.066,.072,57.664
 4983.500,70.220,50.413,76.085,-53.177,14.241,19.836,7.849,2.656,.085,.032,.060,38.734,-48.163,-35.237,2.743,28.965,28.164,.071,57.549
 4984.000,81.773,55.192,61.950,-48.488,12.229,18.118,7.858,2.670,.080,.023,.057,48.927,-51.380,-30.487,2.753,27.312,23.431,.085,59.505
 4984.500,97.874,66.434,30.664,-43.766,10.217,15.052,7.888,2.661,.073,.028,.062,57.919,-50.385,-25.706,2.755,24.693,17.479,.113,63.559
 4985.000,116.708,85.315,19.035,-39.458,8.568,11.721,7.922,2.640,.068,.041,.078,68.143,-44.943,-21.337,2.764,23.542,13.826,.150,68.735
 4985.500,134.962,112.279,14.205,-35.848,7.410,8.906,7.923,2.618,.067,.054,.104,85.296,-36.314,-17.666,2.885,19.500,10.061,.184,73.530
 4986.000,152.691,143.214,10.519,-33.053,6.549,6.983,7.910,2.605,.071,.061,.135,98.924,-27.722,-14.812,2.991,11.255,6.609,.206,76.612
 4986.500,169.680,169.795,7.494,-31.052,5.893,5.890,7.856,2.601,.075,.064,.173,105.594,-21.868,-12.751,3.000,8.007,6.111,.211,77.383
 4987.000,184.539,186.374,7.163,-29.730,5.419,5.366,7.848,2.602,.077,.063,.204,98.794,-20.403,-11.368,2.990,8.765,6.892,.204,76.310
 4987.500,195.194,193.356,8.357,-28.934,5.123,5.172,7.847,2.607,.076,.060,.214,89.655,-24.402,-10.511,2.936,9.755,7.316,.189,74.289
 4988.000,199.088,192.623,9.045,-28.517,5.023,5.192,7.819,2.614,.075,.056,.197,82.136,-34.983,-10.034,2.916,9.741,7.106,.170,71.586
 4988.500,190.773,182.870,9.015,-28.364,5.242,5.468,7.776,2.622,.073,.051,.151,77.292,-50.698,-9.821,2.852,10.762,7.899,.144,67.936
 4989.000,172.496,161.980,12.606,-28.391,5.797,6.174,7.762,2.632,.072,.046,.105,64.097,-67.072,-9.788,2.788,19.793,15.396,.112,63.379
 4989.500,150.720,132.922,34.416,-28.531,6.635,7.523,7.755,2.644,.070,.038,.069,53.326,-79.658,-9.867,2.750,46.037,37.089,.079,58.635
 4990.000,128.661,103.079,92.007,-28.719,7.772,9.701,7.760,2.661,.067,.028,.048,47.597,-85.925,-9.994,2.735,75.442,61.493,.052,54.874
 4990.500,108.837,77.674,123.171,-28.893,9.188,12.874,7.763,2.682,.065,.016,.038,43.660,-85.637,-10.109,2.738,76.911,62.471,.038,52.846
 4991.000,91.193,57.785,95.305,-29.004,10.966,17.306,7.760,2.701,.063,.005,.034,47.996,-79.278,-10.159,2.747,65.863,53.236,.034,52.324
 4991.500,73.677,43.326,72.647,-29.021,13.573,23.081,7.760,2.713,.062,-.002,.034,44.998,-67.044,-10.116,2.756,58.212,46.361,.037,52.699
 4992.000,59.242,34.551,62.768,-28.943,16.880,28.943,7.756,2.715,.061,-.003,.035,38.355,-51.667,-9.978,2.758,51.465,40.288,.042,53.512
 4992.500,51.478,31.295,49.683,-28.794,19.426,31.954,7.766,2.710,.061,.000,.037,38.749,-37.647,-9.768,2.756,40.571,31.017,.050,54.522
 4993.000,48.728,32.294,33.527,-28.606,20.522,30.966,7.798,2.700,.061,.006,.040,42.276,-26.358,-9.520,2.753,29.653,21.767,.057,55.606
 4993.500,49.016,35.650,26.106,-28.409,20.402,28.050,7.816,2.686,.060,.014,.044,41.697,-18.003,-9.262,2.747,25.158,18.382,.064,56.601
 4994.000,51.489,40.078,24.526,-28.217,19.422,24.951,7.811,2.669,.058,.024,.048,42.863,-13.011,-9.010,2.741,23.541,17.666,.070,57.404
 4994.500,55.490,45.223,23.195,-28.033,18.021,22.113,7.803,2.654,.055,.033,.052,42.722,-11.010,-8.765,2.734,23.286,17.476,.075,58.074
 4995.000,60.213,50.690,21.420,-27.851,16.608,19.728,7.811,2.644,.055,.039,.055,40.784,-10.783,-8.524,2.731,23.056,16.888,.079,58.690
 4995.500,64.418,55.621,19.707,-27.675,15.524,17.979,7.806,2.642,.057,.040,.058,41.764,-11.031,-8.287,2.733,21.914,15.392,.083,59.193
 4996.000,67.790,59.332,18.603,-27.516,14.751,16.854,7.805,2.648,.060,.036,.061,45.521,-11.568,-8.068,2.741,20.651,13.858,.085,59.470
 4996.500,70.167,61.752,18.738,-27.397,14.252,16.194,7.810,2.660,.063,.029,.064,46.484,-12.314,-7.888,2.754,21.004,13.752,.085,59.583
 4997.000,71.605,63.229,20.004,-27.338,13.965,15.816,7.818,2.677,.067,.019,.066,43.207,-12.957,-7.769,2.767,22.570,14.478,.087,59.788
 4997.500,72.181,64.359,20.600,-27.348,13.854,15.538,7.822,2.691,.071,.011,.067,43.243,-13.131,-7.719,2.777,22.381,15.240,.090,60.258
 4998.000,72.265,65.631,19.303,-27.422,13.838,15.237,7.826,2.696,.073,.008,.066,47.159,-13.239,-7.733,2.782,20.843,14.945,.094,60.735
 4998.500,72.135,66.927,16.523,-27.544,13.863,14.942,7.818,2.687,.072,.014,.066,46.934,-14.299,-7.794,2.775,18.466,13.225,.094,60.796
 4999.000,72.933,67.699,17.472,-27.692,13.711,14.771,7.821,2.664,.069,.027,.067,51.023,-17.218,-7.881,2.761,20.089,15.153,.094,60.791
 4999.500,76.279,68.266,26.004,-27.846,13.110,14.649,7.813,2.626,.064,.049,.074,54.681,-21.490,-7.976,2.745,29.102,22.365,.105,62.402
 5000.000,81.264,70.298,32.057,-27.990,12.306,14.225,7.812,2.567,.058,.084,.092,52.133,-24.727,-8.059,2.728,34.183,26.444,.143,67.715
 5000.500,85.413,74.277,22.293,-28.108,11.708,13.463,7.831,2.482,.052,.133,.123,51.694,-25.402,-8.117,2.714,22.741,17.239,.210,77.154
 5001.000,87.951,77.745,13.818,-28.194,11.370,12.863,7.829,2.387,.049,.189,.185,50.853,-24.962,-8.143,2.722,17.863,10.491,.290,88.552
 5001.500,90.741,78.449,17.892,-28.249,11.020,12.747,7.828,2.309,.049,.235,.261,50.389,-26.037,-8.137,2.750,23.022,10.792,.357,98.062
 5002.000,97.487,78.328,26.752,-28.284,10.258,12.767,7.830,2.270,.053,.258,.309,53.205,-29.300,-8.111,2.783,29.161,13.081,.385,101.919
 5002.500,109.443,82.735,28.984,-28.316,9.137,12.087,7.832,2.275,.056,.254,.338,52.803,-32.367,-8.083,2.827,29.303,13.014,.364,98.944
 5003.000,123.055,95.273,19.156,-28.364,8.127,10.496,7.837,2.318,.057,.229,.355,48.248,-32.064,-8.071,2.886,18.555,9.194,.311,91.524
 5003.500,137.597,114.274,11.371,-28.438,7.268,8.751,7.817,2.384,.055,.191,.361,50.412,-28.612,-8.085,2.954,12.520,8.346,.255,83.574
 5004.000,154.132,135.533,9.771,-28.532,6.488,7.378,7.833,2.450,.055,.152,.357,45.441,-24.344,-8.118,2.991,11.724,8.243,.217,78.208
 5004.500,170.826,157.079,9.379,-28.628,5.854,6.366,7.836,2.503,.060,.121,.353,19.713,-20.981,-8.154,3.014,10.339,7.091,.205,76.537
 5005.000,185.474,178.317,8.367,-28.714,5.392,5.608,7.833,2.541,.069,.099,.360,2.377,-19.259,-8.179,3.060,8.544,6.053,.211,77.301
 5005.500,195.320,195.637,7.399,-28.786,5.120,5.111,7.839,2.570,.079,.082,.373,.059,-19.619,-8.191,3.122,7.716,5.697,.215,77.937
 5006.000,195.495,202.509,6.725,-28.856,5.115,4.938,7.842,2.597,.084,.066,.375,-999.250,-23.233,-8.201,3.149,7.257,5.445,.204,76.432
 5006.500,186.593,194.145,7.314,-28.949,5.359,5.151,7.819,2.624,.082,.050,.363,-999.250,-31.655,-8.234,3.133,8.292,6.245,.176,72.360
 5007.000,174.438,171.613,10.574,-29.091,5.733,5.827,7.760,2.654,.078,.033,.378,-999.250,-43.604,-8.315,3.206,13.587,9.842,.135,66.633
 5007.500,160.965,142.773,19.769,-29.304,6.213,7.004,7.739,2.682,.074,.016,.502,-999.250,-54.736,-8.468,5.326,24.434,16.771,.095,60.876
 5008.000,147.051,116.844,37.558,-29.596,6.800,8.558,7.716,2.696,.069,.008,.847,-999.250,-61.521,-8.699,2.381,36.135,24.668,.065,56.687
 5008.500,131.522,98.267,59.378,-29.949,7.603,10.176,7.710,2.681,.064,.017,1.433,-999.250,-61.708,-8.992,2.588,46.184,31.977,.052,54.834
 5009.000,114.815,87.037,48.337,-30.319,8.710,11.489,7.610,2.635,.059,.044,1.756,-999.250,-55.036,-9.302,2.620,36.638,25.201,.053,55.027
 5009.500,97.424,80.207,20.745,-30.643,10.264,12.468,7.165,2.576,.063,.078,1.673,-999.250,-43.293,-9.565,2.616,17.987,12.710,.061,56.136
 5010.000,83.586,73.423,13.141,-30.862,11.964,13.620,6.913,2.532,.081,.104,1.065,-999.250,-32.596,-9.724,2.527,13.949,10.095,.067,56.951
 5010.500,75.293,64.902,20.014,-30.942,13.281,15.408,6.905,2.518,.111,.112,-.005,-999.250,-28.717,-9.744,2.607,22.290,15.511,.067,56.955
 5011.000,73.881,57.321,33.642,-30.885,13.535,17.445,6.901,2.531,.145,.105,-999.250,-999.250,-31.833,-9.627,-999.250,31.225,22.404,.062,56.279
 5011.500,78.261,54.306,43.599,-30.724,12.778,18.414,6.900,2.554,.173,.091,-999.250,-999.250,-37.094,-9.405,-999.250,32.147,23.020,.056,55.391
 5012.000,83.356,56.536,41.083,-30.501,11.997,17.688,6.904,2.576,.190,.079,-999.250,-999.250,-38.973,-9.122,-999.250,25.689,18.197,.049,54.443
 5012.500,86.220,62.401,30.148,-30.257,11.598,16.025,6.914,2.590,.200,.070,-999.250,-999.250,-35.651,-8.818,-999.250,20.416,14.380,.042,53.439
 5013.000,87.519,70.168,20.387,-30.021,11.426,14.252,6.920,2.597,.204,.066,-999.250,-999.250,-28.572,-8.521,-999.250,16.743,11.721,.045,53.855
 5013.500,88.560,78.255,15.382,-29.818,11.292,12.779,6.926,2.595,.206,.067,-999.250,-999.250,-20.484,-8.258,-999.250,13.320,9.155,.065,56.734
 5014.000,90.005,84.676,12.580,-29.670,11.111,11.810,6.915,2.590,.206,.070,-999.250,-999.250,-14.359,-8.049,-999.250,9.758,7.056,.087,59.857
 5014.500,92.620,87.878,12.417,-29.595,10.797,11.380,6.926,2.589,.205,.071,-999.250,-999.250,-12.310,-7.914,-999.250,6.731,5.907,.096,61.044
 5015.000,96.516,88.180,14.436,-29.603,10.361,11.340,6.918,2.599,.203,.065,-999.250,-999.250,-13.984,-7.862,-999.250,5.366,5.641,.092,60.538
 5015.500,101.033,87.154,16.124,-29.688,9.898,11.474,6.954,2.633,.201,.045,-999.250,-999.250,-17.316,-7.886,-999.250,5.151,5.617,.085,59.578
 5016.000,104.001,86.036,16.686,-29.836,9.615,11.623,9.832,2.704,.190,.004,-999.250,-999.250,-20.000,-7.974,-999.250,5.100,5.579,.082,59.083
 5016.500,103.176,85.138,16.745,-30.036,9.692,11.746,16.068,2.819,.159,-.064,-999.250,-999.250,-20.681,-8.113,-999.250,5.050,5.544,.082,59.167
 5017.000,98.433,83.914,16.748,-30.287,10.159,11.917,-999.250,2.979,.091,-.157,-999.250,-999.250,-19.312,-8.304,-999.250,5.033,5.538,.084,59.318
 5017.500,91.688,81.213,16.749,-30.597,10.906,12.313,-999.250,3.176,-.031,-.273,-999.250,-999.250,-16.714,-8.554,-999.250,5.001,5.501,.082,59.053
 5018.000,86.018,76.237,16.752,-30.970,11.625,13.117,-999.250,3.405,-.220,-.407,-999.250,-999.250,-14.275,-8.867,-999.250,5.004,5.508,.077,58.334
 5018.500,82.658,69.891,16.760,-31.398,12.098,14.308,-999.250,3.661,-.486,-.556,-999.250,-999.250,-12.735,-9.234,-999.250,4.949,5.461,.070,57.457
 5019.000,81.817,64.720,16.769,-31.856,12.222,15.451,-999.250,3.943,-.834,-.721,-999.250,-999.250,-12.310,-9.632,-999.250,4.225,4.747,.067,57.048
 5019.500,82.087,62.699,16.774,-32.313,12.182,15.949,-999.250,4.263,-1.266,-.908,-999.250,-999.250,-12.258,-10.029,-999.250,2.560,3.129,.071,57.482
 5020.000,80.891,63.099,16.779,-32.736,12.362,15.848,-999.250,.000,.050,1.585,-999.250,-999.250,-10.984,-10.391,-999.250,1.697,2.293,.076,58.220
 5020.500,76.433,62.903,16.783,-33.100,13.083,15.898,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-6.738,-10.694,-999.250,1.602,2.202,.077,58.347
 5021.000,70.123,59.226,16.642,-33.386,14.261,16.884,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,1.306,-10.920,-999.250,-999.250,-999.250,.070,57.381
 5021.500,64.467,51.886,14.202,-33.587,15.512,19.273,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,13.534,-11.061,-999.250,-999.250,-999.250,.057,55.581
 5022.000,59.889,43.431,6.162,-33.703,16.698,23.025,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,31.209,-11.116,-999.250,-999.250,-999.250,.044,53.714
 5022.500,56.395,36.176,.751,-33.738,17.732,27.642,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,55.531,-11.092,-999.250,-999.250,-999.250,.035,52.398
 5023.000,56.908,30.458,.019,-33.702,17.572,32.832,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,85.327,-10.995,-999.250,-999.250,-999.250,.029,51.642
 5023.500,59.587,26.189,-999.250,-33.604,16.782,38.183,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,122.576,-10.836,-999.250,-999.250,-999.250,.026,51.159
 5024.000,60.057,24.990,-999.250,-33.450,16.651,40.015,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,170.731,-10.622,-999.250,-999.250,-999.250,.024,50.832
 5024.500,56.963,29.833,-999.250,-33.245,17.555,33.520,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,231.139,-10.357,-999.250,-999.250,-999.250,.022,50.646
 5025.000,53.956,42.640,-999.250,-32.999,18.534,23.452,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,302.442,-10.051,-999.250,-999.250,-999.250,.022,50.571
 5025.500,53.709,62.271,-999.250,-32.728,18.619,16.059,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,386.928,-9.720,-999.250,-999.250,-999.250,.022,50.592
 5026.000,53.215,83.480,-999.250,-32.461,18.792,11.979,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,499.650,-9.392,-999.250,-999.250,-999.250,.022,50.631
 5026.500,51.104,99.372,-999.250,-32.240,19.568,10.063,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,660.803,-9.111,-999.250,-999.250,-999.250,.021,50.418
 5027.000,48.049,107.275,-999.250,-32.119,20.812,9.322,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-8.929,-999.250,-999.250,-999.250,.009,48.797
 5027.500,47.141,109.756,-999.250,-32.168,21.213,9.111,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-8.918,-999.250,-999.250,-999.250,-.036,42.443
 5028.000,47.105,110.173,-999.250,-32.469,21.229,9.077,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-9.159,-999.250,-999.250,-999.250,-.132,28.753
 5028.500,50.269,110.142,-999.250,-33.095,19.893,9.079,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-9.724,-999.250,-999.250,-999.250,-.246,12.757
 5029.000,45.790,110.113,-999.250,-34.079,21.839,9.082,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-10.648,-999.250,-999.250,-999.250,-.317,2.650
 5029.500,13.423,110.232,-999.250,-35.381,74.501,9.072,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-11.889,-999.250,-999.250,-999.250,-.341,-.800
 5030.000,.000,110.562,-999.250,-36.868,100000.000,9.045,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-13.316,-999.250,-999.250,-999.250,-.346,-1.434
 5030.500,.000,110.995,-999.250,-38.343,100000.000,9.009,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-14.731,-999.250,-999.250,-999.250,-.346,-1.497
 5031.000,.000,111.290,-999.250,-39.603,100000.000,8.986,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-15.930,-999.250,-999.250,-999.250,-999.250,-999.250
 5031.500,2.763,110.878,-999.250,-40.517,361.951,9.019,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-16.785,-999.250,-999.250,-999.250,-999.250,-999.250
 5032.000,2.509,106.511,-999.250,-41.065,398.556,9.389,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-17.272,-999.250,-999.250,-999.250,-999.250,-999.250
 5032.500,.636,88.794,-999.250,-41.321,1571.791,11.262,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-17.468,-999.250,-999.250,-999.250,-999.250,-999.250
 5033.000,.000,50.400,-999.250,-41.406,100000.000,19.841,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-17.492,-999.250,-999.250,-999.250,-999.250,-999.250
 5033.500,.000,6.804,-999.250,-41.428,100000.000,146.968,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-17.454,-999.250,-999.250,-999.250,-999.250,-999.250
 5034.000,.000,.000,-999.250,-41.480,100000.000,100000.000,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-17.446,-999.250,-999.250,-999.250,-999.250,-999.250
 5034.500,.000,.000,-999.250,-41.660,100000.000,100000.000,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-17.565,-999.250,-999.250,-999.250,-999.250,-999.250
 5035.000,.000,.000,-999.250,-42.136,100000.000,100000.000,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-17.981,-999.250,-999.250,-999.250,-999.250,-999.250
 5035.500,.000,.000,-999.250,-43.199,100000.000,100000.000,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-18.984,-999.250,-999.250,-999.250,-999.250,-999.250
 5036.000,.000,2.203,-999.250,-45.246,100000.000,453.889,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-20.970,-999.250,-999.250,-999.250,-999.250,-999.250
 5036.500,.000,2.191,-999.250,-48.636,100000.000,456.504,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-24.299,-999.250,-999.250,-999.250,-999.250,-999.250
 5037.000,.000,2.101,-999.250,-53.449,100000.000,475.881,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-29.053,-999.250,-999.250,-999.250,-999.250,-999.250
 5037.500,-999.250,1.747,-999.250,-59.298,-999.250,572.408,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-34.841,-999.250,-999.250,-999.250,-999.250,-999.250
 5038.000,-999.250,.984,-999.250,-65.369,-999.250,1016.755,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-40.851,-999.250,-999.250,-999.250,-999.250,-999.250
 5038.500,-999.250,.094,-999.250,-70.752,-999.250,10677.230,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-46.174,-999.250,-999.250,-999.250,-999.250,-999.250
 5039.000,-999.250,.000,-999.250,-74.826,-999.250,100000.000,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-50.188,-999.250,-999.250,-999.250,-999.250,-999.250
 5039.500,-999.250,.000,-999.250,-77.459,-999.250,100000.000,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-52.761,-999.250,-999.250,-999.250,-999.250,-999.250
 5040.000,-999.250,.000,-999.250,-78.912,-999.250,100000.000,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-54.153,-999.250,-999.250,-999.250,-999.250,-999.250
 5040.500,-999.250,.000,-999.250,-79.596,-999.250,100000.000,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-54.777,-999.250,-999.250,-999.250,-999.250,-999.250
 5041.000,-999.250,.000,-999.250,-79.870,-999.250,100000.000,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-54.991,-999.250,-999.250,-999.250,-999.250,-999.250
 5041.500,-999.250,.000,-999.250,-79.965,-999.250,100000.000,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-55.025,-999.250,-999.250,-999.250,-999.250,-999.250
 5042.000,-999.250,.000,-999.250,-79.992,-999.250,100000.000,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-999.250,-54.992,-999.250,-999.250,-999.250,-999.250,-999.250

