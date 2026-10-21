# 10.0 Spotting, Reconnaissance & Detection

10.0 SPOTTING UNITS
Detecting enemy ships in the Pacific’s vast expanse
was difficult, and even amid the clustered islands of
some of the larger chains it was a challenge. What can’t
be seen can’t be destroyed, and reconnaissance is the
eyes and ears of the wise commander.
Spotting is an important aspect of the game. If you have
the “Fog of War” settings On, only enemy units that
have been spotted will be visible on the map. Messages
announcing enemy ships sunk may not appear,
depending on the Detection Level (see 10.1 Detection Levels), while messages regarding
enemy ships sinking should only come up sometimes, with the probability equal to the DL
times 10 percent. In addition, the Intel screen will not list sunk enemy ships for up to 60 days,
or points for damaged enemy ships.
Spotting is performed in several ways:
     »» Aerial reconnaissance Missions take photos of bases and
        ground troops, giving you intelligence on what is there.
     »» Bombing Missions also take photos of their combat Missions for
        bomb damage assessment, though the results aren’t as good.
     »» Naval spotter planes perform Naval Searches that can spot enemy
        ships. Note that TF’s are less likely to be spotted when naval
        search aircraft are more than 300 miles from their base.
     »» Coast Watchers were civilians or soldiers that reported on enemy
        naval movements. When a Coast Watcher spots an enemy unit,
        it’s noted during the special Coast Watcher Spotting phase.
     »» Ground units spot enemy ground units in their hex and all adjacent hexes.

10.1 DETECTION LEVELS (DLS)
When the Fog of War option is On, every ground unit, TF, and minefield on the map must be
spotted before it is visible for the enemy to see. If the Fog of War is Off, then all these units are
always visible on the map to the enemy player, but the units in the game will not act as if they
have total knowledge of the enemy. In War in the Pacific, Admiral’s Edition™, each of these
units, as well as each base, has a Detection Level (DL) and a Maximum Detection Level (MDL),
both between 0 and 10. The DL indicates very recent intelligence about the enemy and it is
the DL that has an impact on combat results. The MDL represents a general awareness of the



enemy based on both recent and less current information, and it is this level that is used to
determine which enemy units are placed on the map.
An MDL of zero indicates the unit has not been spotted by the enemy and is not shown on the
map (enemy bases are always shown on the map even if a base has an MDL of zero nothing
but the name of the base will be known by the enemy). MDL’s above zero indicate the enemy
has spotted the unit. When Fog of War is Off, all units have a minimum MDL value of one. The
greater the MDL, the more is likely to be known about the unit by the enemy and displayed
on the screen.
The greater the DL the easier it is to inflict damage on the enemy in combat. Often even
when the DL is zero, friendly forces will take action due to an MDL value that is higher (i.e.
even though an enemy TF disappears at night, expectations of enemy movements based
on following the enemy closely the previous day can lead to friendly forces anticipating the
enemy’s next move). The DL of every unit changes constantly during the resolution phase
based on the unit’s activities and enemy actions.

10.1.1 CHANGING DETECTION LEVELS
The following items change the DL of a particular unit:

10.1.1.1 DL OF NAVAL TASK FORCE
 Add 1 to DL         TF spotted by search aircraft (per aircraft that spots
                     the TF – only notified of first plane each phase)
 Add 2 to DL         TF attacked by search aircraft
 Add 2 to DL         TF has Air Combat Mission and it reacts to an enemy TF
 Add 1 to DL         TF has carrier(s) launching a strike Mission (per
                     air unit that attacks/escorts from TF)
 Add 1 to DL         Japanese TF moves into coastal hex with y coordinate>30
                     and sighted by coastwatcher during daylight 75% chance
                     of sighting, during Night 50% chance of sighting, also if
                     daylight phase then second chance of adding 1 if DL is still 0
                     after first check). This also happens at the beginning of each
                     resolution phase for each Japanese TF in a coastal hex.
 Add 1 to DL         TF spotted by enemy sub
 Add 1 to DL         TF attacked by enemy sub
 Add 1 to DL         TF is a sub TF that is attacked by an enemy ship




                                                                                      Spotting


 Add 1, 2, or           TF is spotted by a recon flight (see 10.2 Recon Flight section below)
 4 to DL
 Set DL to 0            All Task Forces at the very beginning of each
                        Day and Night resolution phase


10.1.1.2 DL OF A BASE
 Add 1, 2, or 4 to DL         Base is spotted by a recon flight (see 10.2
                              Recon Flight section, below)
 Subtract 1 from DL           End of each Day and Night Resolution Phase
                              (essentially once every 12 hours)


10.1.1.3 DL OF A GROUND UNIT
 Add 1 to DL                  Unit is involved in ground combat (attack or defense)
 Add 1 to DL                  Unit fires AA weapon in defense of base or ground unit
 Add 1 or 2 to DL             Unit fires naval gun or dual purpose gun at
                              enemy ships (randomly adds 1 or 2)
 Add 1, 2, or 4 to DL         Ground unit is spotted by a recon flight (see
                              10.2 Recon Flight section, below)
 Halve DL                     Unit enters a new hex by marching
 Set DL to 0                  Unit is air transported
 Subtract 1 from DL           End of each Day and Night resolution phase
                              (essentially once every 12 hours)
 Add 1 to DL                  Whenever in a hex with an enemy ground unit
 If DL=0, set DL=1            Whenever in a hex adjacent to an enemy ground unit




10.1.1.4 DL OF A MINEFIELD
 Add 1 to DL                Ship hits mine in minefield
 Add 1 to DL                Minesweeper clears a path in the minefield
 Add 1 or more to DL        Minesweeper widens a path in the minefield
 Add 10 to DL               Enemy minefields in hex with enemy base when
                            the base is captured by friendly forces


10.1.2 HOW MAXIMUM DETECTION LEVELS CHANGE
MDL’s go up with the DL value, but they decline at a slower rate than the DL. Whenever any
enemy DL value increases, if the MDL of the enemy is lower than the new DL, the MDL is set
equal to the new DL.
Whenever an event causes a reduction in the DL (including ships with DL’s already at zero)
and the new DL value is zero, the MDL is reduced by one. In this way the MDL can remain a
positive number long after the DL has become zero. However, MDL’s for subs are cut in half
(rounded down) every 12 hours.

10.2 RECON FLIGHTS
Whenever a plane flying a recon Mission reaches its target hex or an air unit bombs a target,
every enemy ground unit, TF or base (not minefield) in the hex has a possibility of having its
DL increased by 1, 2 or 4.
Each enemy unit is checked separately to see if the pilot has successfully spotted the unit:
     »» If a recon aircraft type is flying a Recon Mission, the percentage
        chance that any given unit will have its DL increased is equal to the
        Experience of the pilot. If the DL is increased, it will increase by 4.
     »» If a non-recon type plane is flying a Recon Mission, the percentage chance
        that any given unit will have its DL increased is equal to the Experience
        of the pilot divided by 2. If the DL is increased it will increase by 2.
     »» If an air unit bombs any enemy target, the percentage chance that any
        given unit in the target hex will have its DL increased is equal to the
        Experience of the one pilot chosen at random to take reconnaissance
        photos divided by 2. If the DL is increased it will increase by 1.




                                                                                       Spotting


10.3 RADAR DETECTION LEVELS AND SURFACE COMBAT
When TFs enter into Surface Combat, each ship is given an individual DL for purposes of the
combat resolution only. Each ship with radar will attempt to use its radar to increase the DL
of enemy ships involved in the combat by checking its radar against each enemy ship. Each
successful radar check will increase the DL of an enemy ship by one. Ships that are on fire will
have high DL values at night. (The most dangerous place to be is on a burning ship during a
night surface engagement.) The higher a ship’s DL during surface combat, the more likely it is
to become the target of an enemy ship’s weapons.

10.4 INFORMATION GIVEN REGARDING
ENEMY UNITS/BASES/MINEFIELDS
During the Orders Phase, you are able to view information about enemy ground units, Bases,
Task TFs, and minefields that have a MDL greater than zero. Once detailed information is given,
the amount of error in the information will decline over time if the MDL level stays high as
friendly forces try to refine their estimates of the enemy.
When the MDL of an enemy unit is equal to 1, only the location and unit type information is
displayed.
If the MDL of a unit is greater than 1, than there is a chance that approximate numbers of
more detailed information will be revealed about the unit. The greater the MDL the greater the
chance that detailed information will be given.
If the MDL of a ground unit is above 1, an estimated number of troops, guns, and vehicles may
be provided. If the MDL of a base is above 1, the damage to the port and airfield (average of
runway and service damage) and the number of fighters, bombers and auxiliary aircraft at the
airfield may be provided.
If the MDL of a TF is above 1, then you will receive a list of ship classes of ships that have been
positively identified and an estimated total number of ships in the TF. If the MDL of a minefield
is above 1, the minefield will be displayed on the map. No additional information is ever given
about enemy minefields.
Production items have the DL of the base they are located at. All Factory information initially
displayed in the rollover text for an enemy factory is 100% correct. This information will only be
updated when the DL of a base increases. Thus, even though Tokyo could have expanded and
converted many of their factories, until the first recon flight flies over Tokyo, the roll over text
may show Tokyo with the production stats it had at the beginning of the scenario.
Several minefields can exist within the same hex but minefields are represented on the map
by only one minefield symbol per hex.
