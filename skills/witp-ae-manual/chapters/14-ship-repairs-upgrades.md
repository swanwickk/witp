# 14.0 Ship Repairs, Conversions & Upgrades

14.0 SHIP UPGRADES,
CONVERSIONS AND REPAIRS
14.1 SHIP UPGRADES AND CONVERSIONS
Upgrades and Conversions are similar in many ways, but differ in one important respect. The
AI is only able to Upgrade a ship; it is not able to perform a Conversion. Conversions are player
options and, as such, are not available to the AI.
Ships may Upgrade or Convert by clicking on the highlight Upgrade or Convert field on the Ship
Information Screen. Clicking on either field will bring up a screen that shows the characteristics



                                                                                  Production

of the ship being Upgraded or Converted to. There is an additional conversion option available
to the Japanese player, an “AK Carry Troops” option.

14.1.1 UPGRADES
Upgrade: Clicking on the Upgrade field brings up an Upgrade screen that shows the
characteristics of the ship type of the next allowable upgrade. A “Next Upgrade” button allows
the player to cycle through all the Upgrades available to the ship. A Unit Information section, at
the right of the screen, shows the unit information of the target ship, as well as the Upgrade
timing, damage and yard requirements. When a ship is being Upgraded or Converted, it is taken
off-line and will not appear in the ship list for the port.
Upgrade System Damage: is the amount of system degradation that will occur in the course
of the upgrade/conversion.
Upgrade Engineering Damage: is the amount of engineering degradation that will occur in
the course of the upgrade/conversion, and is a function of the difference between the speed of
the original and the upgraded/converted ship.
Upgrade Flotation Damage: is the amount of flotation degradation that will occur in the
course of the upgrade/conversion, and is a function of the difference between the original and
the upgraded/converted durability values.
Upgrade Delay: is the minimum time, in days, the ship will be taken offline in order to effect
the upgrade/conversion.
Shipyard Size: is the minimum Repair Shipyard size necessary to effect the upgrade/
conversion. When this value is “0”, upgrades/conversions can be made at Ports with a sufficient
“ability” rating, as explained in the Port Section, below.

14.1.2 CONVERSIONS
Conversion: The Conversion field shows the ship ‘types’ that the current ship may convert to.
Clicking on the Conversion field brings up a Conversion screen that shows the characteristics
of the ship types of the ‘Convert to’ options; clicking on the yellow highlight for each ship type,
brings up the characteristics for that type. Conversions have the same damage, delay, and
shipyard requirements as Upgrades. However, they are not available to the AI.
AK Carry Troops: Clicking on the “Convert Cargo Space to Carry Troops” button will allow
certain Japanese cargo ships to convert 1/3 of their cargo carrying capacity into troop carrying
capacity. This option does not require the ship to be in a repair yard, but the ship must be in a
Port of level 7 or greater. It takes approximately 7-14 days to make this conversion (depending
on size of ship and of location where conversion is taking place).



                                                                               Production


14.2 DAMAGE AND REPAIRS
Damage and Repair: Damage and Repair have been extensively redone. For human players
repairs are now flexible and depend on the availability of appropriate Ports, Repair Shipyards,
Repair Ships and Tenders, the presence of Naval Support squads, and the type and degree of
damage, as well as the specific systems (i.e., weapons, etc) that have been damaged. Port size
and Port capability now plays a major role in determining where a ship should be repaired, and
how long the repair process takes.
Once a ship is in a suitable repair port, a player has several options available as to how the
repairs are conducted. Repairs can be done at anchor, by the ship crew; at anchor, by the ship
crew assisted by Repair Tenders; at dockside, by the crew, assisted by port facilities, and any
available Tenders or perhaps at a Repair Shipyard.

 Port     Largest      Total         Max        Fueling    Rearm        Pt        Pt   Pt Wpns
 Size       Ship       Ships        Cargo                             Repair    Assist Repair
          Docked     Docked In     In Tons                            Assist     Ops
          In Port    Port (tons)
           (tons)
 0       0            0            0           0            0         0         0         0
 1       6.000        6.000        2,500       2,500        15        8         8         25
 2       9,000        12,000       6,250       6,250        25        27        34        50
 3       12,000       24,000       11,250      11,250       40        27        81        75
 4       24,000       48,000       18,750      18,750       110       38        152       100
 5       36,000       60,000       33,000      25,000       300       50        250       125
 6       48,000       84,000       54,500      27,500       700       63        378       150
 7       60,000       104,000      72,800      34,375       5500      77        539       175
 8       72,000       128,000      108,800     62,500       6000      92        736       200
 9       78,000       172,000      150,500     93,750       6500      108       972       225
 10      84,000       196,000      176,000     125,000      9999      125       1250      250

         Note: Due to the complexity of the repair system for human
         players, the AI uses a simpler repair system similar to the
         original game.



14.2.1 DAMAGE AND REPAIRS
Ships receive damage to guns and topside structure (System Damage), the hull (Floatation
Damage), and propulsion/power plants (Engine Damage). There are two degrees of damage,
Normal Damage and Major Damage. Normal Damage may be repaired almost anywhere (with
large differences in repair time, of course), but Major Damage can only be repaired at a suitably
sized Port or Repair Shipyard, or for small craft or low levels of major damage, at a port or
alongside a repair ship or tender. Major Floatation Damage can be repaired by an ARD, but
an ARD cannot repair any other type of damage. Repair ships (AR) can repair major engine
damage.

14.2.1.1 DAMAGE REPAIR SELECTION
The damage type with the highest level will “usually” be repaired first. Damage Levels are
considered in “bands”, with the first “band” being any damage type greater than 90. The
“bands” decrease in increments of 15 until a value of 15 is reached; then the “bands decrease
by approximately a factor of 2 (i.e., 15, 8, 4, 2, 1).
Selection In-Band. Within a “band”, damage type is checked in a specific cycle: Floatation,
Engine, System. This ensures a ship in danger of sinking will have its Floatation Damage
repaired first.
Selection Across-Band. “Bands” are devised so that damage types are repaired in stages,
rather than all of one type before any of another. Floatation damage and major engine damage
are given higher priority by offsetting damage levels for band calculations. Major floatation
damage is tripled, regular floatation damage and major engine damage are doubled. This
means that floatation damage will be considered to be in approximately the same band as
systems damage of up to twice that much, three times that much if the damage was Major
floatation damage.

14.2.1.2. WEAPONS DAMAGE
Notwithstanding the amount of System Damage, repairs to guns (or anything else specifically
listed on the Ship’s Information screen) are also limited. A Gun Repair value is calculated for
each Repair Type and only guns (or other weapon systems) ‘costing’ up to this value can be
repaired. It is possible for a ship to have its hull, engines and systems substantially repaired
without having its weapon systems repaired. A DD, for example, might get hull, engine, and
electronics repairs at a moderate sized port, but must go to a better repair facility for repairs to
torpedo tubes or its primary gun batteries.




                                                                                 Production

14.2.1.3 CATASTROPHIC EVENTS
There is always the possibility of an untoward “event” occurring in the course of a repair that
results in the catastrophic destruction of the ship. During any repair, there is a .01% to .0125%
chance of a catastrophic “event”.

14.2.1.4 REPAIR OF MAJOR DAMAGE
For most ships, large amounts major damage can only be repaired in a shipyard or by a repair
ship or an ARD (in certain circumstances). For small craft, major damage can also be repaired
at a port or alongside a tender.For PT Boats, Motor Gun Boats, Motor Launches, Patrol Craft,
Patrol Boats, Sub Chasers, Minesweepers, Yard Minesweepers, Coastal Minesweepers, Yard
Patrol Craft, and Harbor Defense Motor Launches: Major damage can be repaired by a size 4
port (or larger), except for ships with a tonnage greater than 499, which require a port of size
tonnage/100. Major damage can also be repaired by an AR, AD, AG, or AGP if available.
For Barges (LB, LCVP, LCM, LCT): Same as above except no tonnage check on the port size and
AD excluded (just AR, AG, AGP).
For Midget Submarines: Major Engine Damage can be repaired by a port of size 6 or greater, or
by an AR or AS. Major Float Damage still requires a shipyard or ARD.
For Merchant ships (xAP, xAPc, xAK, xAKL, TK), small cargo ships, yard oilers and transports
(AKL, YO, APc): Major damage can be repaired at a port with size equal to 100 per ship tonnage.
That is, a level 1 port can repair ships of 1-100 tons, a level 2 can repair ships of 101-200
tons, etc.
Repair ships (AR) can repair all major damage for Small Craft. They can also repair major
engine damage of 5 points or less and major flotation damage of 5 points or less on any ship.
Ports of size 7 and above can also repair major engine and major floatation damage of five
points or less, but only if the ship is taken offline (assigned to pier side repair mode).

14.2.2 GAMEPLAY
Once a ship is damaged and directed to an appropriate Repair Facility, the player has a number
of options as to how to schedule repairs.
Assignment to repair facilities is done from the Ship Display screen or from the Manage ships
under repair button on the List of Ships in Port screen.

14.2.2.1 FROM THE SHIP DISPLAY SCREEN
When a ship is in port, the lower right hand corner of the ship display screen shows the current
state of repair for that ship. If the ship is undamaged, this area will say Under Repair: No



If the ship is damaged, this area shows the estimate (in days) for the repairs to be done and
the Repair Type, which is either Readiness or Stood Down. The default mode of repair will be
Readiness Repair, which is the ship’s own crew trying to fix all the damage. If port facilities or
repair ships are available, they will supply some assistance. In this mode, the ship is constantly
ready for sea, so repair is less efficient. For all other repair types, the ship must be Stood Down
or taken out of service for repair. Taking the ship out of service has a chance of adding 1-2
to the Sys damage due to equipment failures during the shut-down process. Restoring a ship
from Stood Down state before repairs are complete incurs a delay of 1-3 days for the ship
systems to all come back online.
If a ship is changed from Readiness to Stood Down, a few more lines appear, allowing the
player to select the type of offline repair, and the priority. Two round buttons appear allowing
the player to set or cancel the changes. For Stood Down repairs, there are 3 Repair Modes:
      »» Pierside
      »» Repair Ship
      »» Shipyard
Clicking on the type cycles through the options. The estimated time for repair for each type
will show above in the Estimate Time field. Sometimes Pierside can be the fastest repair type.
This is due to the nature of the damage and the time it takes to stand down the ship and
bring it back to readiness. The time required to return a ship to service is built into the repair
estimate.
If a Repair Ship is not available to assist (either none in port or all in port are busy with other
repairs), the option will not be selectable when the Repair Mode is clicked. Similarly if there
is no Shipyard, or the Shipyard does not have capacity for the ship selected, it will not be
selectable. In some cases, nothing will happen when Pierside is clicked because the other
options are not available.
The Priority toggles between the two each time you click it. The estimated time reflects the
current setting of this field.
When you click Set Changes, whatever is the current selection will be the orders for that ship.
If you change your mind, there may be a delay in getting the ship back to Readiness. If you
click Cancel Changes, the repair settings go back to what they were with no penalty. Leaving
the Ship Display screen with changes pending sets those changes as if you clicked the Set
button.




                                                                                    Production

14.2.2.2 MODIFY REPAIR FOR EVERY DAMAGED SHIP IN PORT
Another option for ship repair is to view and manage the repair for all ships in a port at the
same time. Click on the Manage ships under repair button on the Ships in Port screen to bring
up the Repair screen, which shows all ships in port with damage.
By default all ships with damage will have their own crews trying to fix the damage. This mode
is called Readiness repair because the ship is ready to leave port at any time. All the other
repair modes require that the ship be stood down from operational readiness for the repairs to
be done. When the ship is stood down, there is a time delay for shutting off ship’s systems and
then another delay for bringing the ship back online. For Shipyard repair there is also a delay
for putting the ship into dry dock and taking it out. Because of these delays, some damage
might be faster to fix with less involved repair modes.
The Repair Screen shows all the ships in port with damage. The bottom of the screen shows
the ship with the current focus. By default, it’s a ship chosen at random. To change the ship in
focus, click on the name of the ship from the list, change the priority, or change the repair
mode. At the bottom of the screen, you will be given choices about what to do with that ship
and estimated repair times for the different modes of repair. These are only estimates and the
real repair times will vary based on random factors as well as the work load in the port
repairing other ships.




It is possible to over assign ships to any of the port’s facilities. If the shipyard is overloaded, a
message in red will appear below the list of ships indicating the current tonnage assignments.
If any port facility is overloaded, the repair facilities will try to get to ships as best they can.
As ships are repaired, the ones that have been delayed will move up in the repair queue. This
enables a player to assign a large number of ships to repair in a port and leave it up to the port
to fix them as soon as they can get to them.


Shipyards and Repair Ship repair will only be available if the port has those repair abilities in
port. Repair ships cannot repair if they are in a task force docked at a port.
Once the Repair Screen is closed, or another ship is selected, the repair selections picked
are set for that ship. During the same turn, a player can go back and change their choices for
repair for that ship, however, any Sys damage accumulated from setting that ship to a stood
down repair mode will remain. This represents damage that happened to the ship while the
crew started to shut down systems for repair. If a ship was set to a stood down mode and then
changed to Readiness in the same turn, it will not incur a delay for bringing back into service.

14.2.3 REPAIR TYPES:
Ships can be repaired using one of four different repair modes. Of the 4 types of repair, 3
require that the ship be “stood down” for repairs. When a ship is stood down, it is unavailable
for service and if it is put back into service before it is repaired, it will usually incur a delay. The
delay in putting a ship back into service is built into the repair estimates for the stood down
repair types. Readiness Repair is the only type of repair that allows a ship to be included in a
task force at any time without delay.
Ships may be repaired and will consume repair capacity, in the following decreasing order:
1) Shipyard Repair, 2) Repair Ship Repair, 3) Pierside Repair, and 4) Readiness Repair. Repairs
are calculated in repair points. It takes 100 repair points to repair 1 damage point, per day.
One half of the daily repair rate is consumed, and one half of the daily repairs are performed,
during each pulse.

14.2.3.1 SHIPYARD REPAIR:
Damaged ships are evaluated for repair, based on their “tonnage”, as well as the extent and
“type” of damage. Repair Yards are able to repair all types of damage; System, Floatation, and
Engineering damage, as well as Major damage. Major Damage requires special treatment for
repair modes other than Repair Yard repairs. Ships being repaired in a Repair Yard get no other
benefit; the yard does it all, and neither Repair Ships nor Naval Support has any effect.
1. Yard Capacity. The Repair Yard must have an available capacity equal to, or greater than, the
“tonnage” of the damaged vessel. Repair Yard capacity is the Shipyard size, times 1000. A size
50 Repair Yard has the capacity to accommodate a vessel of 50,000 tons.
A repair yard can have more tonnage assigned to it than it’s rating (but cannot have a single
ship larger than its tonnage limit). The ships that exceed the capacity of the yard will be put in
a queue and repaired as soon as the yard can manage to get them in. This allows players to
“load up” a yard and leave it to sort out the repairs.
2. Repair Capacity. Repair Yard repair points are the Shipyard size, times 10. For example a size
50 Repair Yard will generate 500 repair points.


                                                                                 Production

3. Priority. Ships may be assigned to one of four possible priorities for repair: Normal, High,
Critical, and Low. High and Critical priority accelerate the completion of repairs, but with a
capacity utilization cost to the Repair Yard. This simulates maximum utilization of available
“yard workers” to repair the High-Priority vessel. Ships on High-Priority will repair at a rate of
1.667 times normal, but with a 2x ops penalty while ships assigned critical priority will repair
at twice normal rate with a four-fold consumption of repair capacity.

14.2.3.2. REPAIR SHIP REPAIR
Several different types of Repair Ships are available to assist in repair of different types of
vessels. The extent of damage that can be repaired by Repair Ships depends on the “kind”
of Repair Ship; for example, an ARD may only repair floatation damage, but may repair Major
floatation damage. ARs and other types may NOT repair Major damage for larger ships. They
can repair major damage to small craft, like PTs and barges. Ships may use the assistance of
Repair Ships in two ways; at anchor, or at dockside. In either mode, the Repair Ships available
to repair different warship types are as follows:

 AR              May assist repair of any ship type. Can repair low levels of Major
                 damage on all ships. Also all Major Damage for small craft.
 ARD             May assist repair of any ship type, but only floatation
                 damage; may repair Major floatation damage.
 AS              May assist repair of submarines only. Cannot repair Major damage
 AD              May assist repair of DDs or any Small Escort types only.
                 Can repair Major damage only for small craft.
 AGP             May assist repair of PT and other Small Craft only.
                 Can repair Major damage for small craft
 AG              May assist repair of Small Escort and Small Craft only.
                 Can repair Major damage only for small craft.
 Small           DE, APD, DMS, DM, AVD, E, TB, KV, PF, PB, PC, SC, AM, ML
 Escort:
 Small           PB, PC, SC, AM, ML, HDML, MGB, YP, YMS, AMc
 Craft:


 14.2.3.2.1 REPAIR SHIP CAPACITY
Repair Ships make repairs based on their capability (shown above) and their available Ops
points calculated turn-by-turn. An undamaged Repair Ship, that does nothing else in a



complete turn, will generate 1000 Ops points in that turn. Ops points are not cumulative. You
must use them, or lose them.

    14.2.3.2.1.1 REPAIR POINTS
Undamaged, “fresh” Repair Ships may contribute, up to a maximum of 83 Repair Points per
turn. Therefore, Repair Ships may repair up to a maximum of 0.83 damage points per turn.

    14.2.3.2.1.2 ARD REPAIR POINTS
ARDs are very efficient at floatation repair, but are limited to hosting a single ship per cycle.
An undamaged, “fresh” ARD may contribute, up to a maximum of, 100 Repair Points per turn.
An ARD may repair, therefore, up to a maximum of 1 floatation damage point per turn on a
single ship.

    14.2.3.2.1.3 PRIORITY REPAIR.
Repair Ships may also repair on a High-Priority basis. In this case, a Repair Ship’s entire
aggregate of Ops points is used and may repair up to a maximum of 1.4 damage points per
turn, with a consequent total Ops point penalty.

14.2.3.3 PIERSIDE REPAIR
Pierside Repair uses the general facilities of a Port to repair ships. If this option is chosen,
there will be no assist from a Shipyard, even if one is available. The ship’s own crew and any
available Naval Support will assist in the repairs. Pierside Repair has two names: Readiness
and Pierside. Readiness Repair is a type of Pierside Repair in which the ship is trying to remain
ready-for sea and therefore incurs a consequent time penalty. A stood down Pierside Repair
implies the ship is powered-down and is not available for operations in the immediate future.
In addition, any available Repair Ships or Tenders can contribute to repair, so long as they are
available after any other ships assigned to Repair Ship repair mode have been handled..
Readiness and Pierside repairs are calculated substantially the same way, except for certain
factors in the calculations. A ship that is being repaired stood down will get better calculation
results and repair damage more quickly because it does not have to be kept constantly readyfor-sea.

14.2.3.4 PORT REPAIR ASSIST
Ports assist in repairs by generating repair points based on their size, adjusted for Port damage.
The table, above, shows the maximum number of Port Assist Repair Points for ports of various
sizes. For example, an undamaged level 6 port generates (contributes) 51 Repair Points.




                                                                                   Production

14.2.3.5 NAVAL SUPPORT ASSIST
Naval Support squads can assist in repairing damage to ships at pierside, either in the stood
down Pierside mode, or normal Readiness pierside mode , and for ships assigned to AR Repair.
Naval Support Capacity - Naval Support available for repair assist is the number of Naval
Support squads up to a maximum of 100 per ship.
Naval Support Repair Points - Naval Support generates Repair Points at the rate of:
     »» (Naval Support/x)–(Damage/5), where ‘x’ is 2 for
        stood down and 3 for Readiness repairs.
     »» For example, 100 Naval Support squads repairing a stood down ship
        with damage of 20 will contribute (100/2) – (20/5) = 46 repair points.
14.2.3.6 CREW ASSIST
A vessel’s own crew contributes Repair Points to the calculation. Crew Assist Repair Points
are (Crew Experience/8). A crew with experience of 80 can contribute 10 Repair Points to the
total.
Example - An undamaged level 6 port, with 100 Naval Support squads, repairing a ship
with damage of 20 and crew experience of 80, that is stood down dockside, will generate
a maximum of 51 + 46 + 10 = 107 Repair Points, and be able to repair approximately 1.07
points of ship damage daily. This translates into a minimum of 18 to 19 days of repair time
for that vessel.

14.2.3.7. TENDER ASSIST
If any Tenders capable of providing repair services are present in port AND no vessels are
assigned to Repair Ship repair mode, the Tenders can contribute to dockside repairs.
Case 1. If the Port Repair + Support Repair value is greater than Repair Ship value, the final
Repair value has a maximum of [Crew + Port + Support + Repair Ship/2]
Case 2. If the Repair Ship value is greater than the Port Repair + Support Repair value, the final
Repair value has a maximum of [Crew + Port + Repair Ship + Support /2]

14.2.3.8 PORT ASSIST OPS
Port Assist Ops determines how many ships can be repaired in a given Port of a given size.
Port Assist Ops calculations only apply to ships being repaired at pierside, whether Readiness
or stood down Pierside. A Port Assist Cost, for each ship under repair, is subtracted from the
Port Assist Ops value. The next ship’s Cost is subtracted from the remainder, etc, until all Port
Assist Ops points are used. The Table, above, shows the maximum number of Port Assist Ops
Points for ports of various sizes. So long as the remaining Port Assist Ops points are greater
than the Port Assist Cost for a given ship, the “full” port repair value is applied to that ship. If

the remaining Port Assist Ops points are less than the Port Assist Cost for a given ship, the port
repair value is just the remaining percentage.

 14.2.3.8.1 PORT ASSIST COST.
The Port Assist Cost per ship is (Damage x 10) + (Ship Tonnage/500), for stood down ships. The
calculation changes to (Damage x 20) + (Ship Tonnage/500) for ships in Readiness repair.

14.2.3.9 READINESS VS. PIERSIDE (STOOD DOWN) REPAIR
Readiness and Pierside (stood down) repairs are calculated substantially the same way, except
for certain factors in the calculations. A ship that is being repaired while stood down will get
better calculation results and repair damage more quickly because it does not have to be kept
constantly ready-for-sea. In general, for Readiness repairs, Port Assist and Naval Support are
approximately 2/3 of the above values.

14.2.4 WEAPON REPAIR:
Repairs to guns and other weapon systems are also limited. A Weapon Repair Level is calculated
for each Repair Type, up to a maximum value. Only guns or weapon systems “costing” up to this
level can be repaired at a suitable Port or at an anchorage with suitable available Tenders.

14.2.4.1 WEAPON REPAIR COSTS:
Weapon Repair points are generated by each Repair Type, independently of their ability to
repair other forms of damage. Weapon Repair points are applied to damaged weapon systems
in terms of Weapon Repair Costs.
Weapon Repair Costs are as follows:

                  Rockets (all types)             50
                  Radars and ASW detectors        90
                  Mines and Torpedoes             120
                  Guns                            Effect value of the gun.


14.2.4.2 WEAPON REPAIR POINTS
The different Repair Types, described above, contribute Weapon System Repair Points, as
follows:
Repair Shipyard - Weapon Repair level is the Shipyard Size (not capacity, but original size)
times 20, up to a maximum of 300.




                                                                                       Logistics

Tender Repair - Tenders are limited in what weapon systems they can repair (as described in
section 14.2.3.2), but to the extent they can repair weapons, their weapon repair points are
set to 250.
Port Repair - To the extent a port can repair weapon systems, its weapon repair points are set
to the port size x 25.
In small scenarios (i.e. not full map), the AI will send damaged ships off map.
