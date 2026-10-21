# 15.0 Logistics, Fuel & Resource Transport

15.0 LOGISTICS
Supply comes in two categories:
     »» Basic supplies, which are used to feed, clothe, arm,
        repair, and build land, sea, and air units.
     »» Fuel, which is used only for naval units.
Each unit (Air, Ground, and Naval) has a minimum requirement of supplies, which is constantly
calculated and updated by the computer. Supply needs are an estimate of future needs based
on recent supply usage. Thus, if aircraft at a base are flying a lot of Missions, or ground units
are engaging in combat at a base, or ships are replenishing ammo from a base, the supply
needs of the base will increase. As combat activity declines, the supply needs value will also
decline, although units always require a basic subsistence level of supplies. While supplies are
actually consumed as used, without adequate supplies on hand to meet the expected needs,
units instinctively begin to curtail operations in order to stretch out the available supplies.
Units that are undersupplied don’t perform at their maximum efficiency, and ships that are
under-fueled are only able to move one hex every day. Units with no supplies operate at about
25% of their peak efficiency.
Supplies are stockpiled at bases. Supplies are created via the production system and can
also come into the game at bases that are assigned a daily allotment. From there they can be
distributed to satellite bases in a variety of ways already described; via air transport, by ships in
TFs, submarines with transport Missions, and overland. A base may transfer supplies, oil, and
resources to an adjacent base regardless of the terrain the separates the two hexes (allows
inland sea movement of resources and oil).
Support troops are required for a base to operate efficiently. Without engineers, bases can’t
be created, expanded, or repaired. Without aviation support, aircraft can’t remain operational,
and without support troops, units at the base will not recover from the fatigue they suffer from
combat and malaria.




15.1 SUPPLY OPERATIONS
Twice a day, during the Supply Needs Calculation and Overland Supply Movement Phases,
the computer calculates the supply needs of all the units and bases in the game. It then looks
for units and bases that need supplies, and which are near bases ((or ground units in the
same hex) that have an abundance of supplies. Supplies are then automatically transported
overland to the needy units and bases if there is a clear supply path on the ground. Many
supply operations occur during the daily Supply Operations Phase.
Ships are limited to loading 10% of the supplies at a base if the base either has less than
30,000 supplies present or its current supply level is less than four times its supply needs.
The Supply Operations Sequence is broken down as follows:
      1. Expend required supply points to maintain ground units and aircraft formations.
      2. Repair aircraft and determine effect of available Aviation Support on the
           readiness of aircraft formations. Add pilots to air units that need them.
      3. Adjust Pilot Morale.
      4. Adjust fatigue of ground units.
      5. Units not at bases construct fortifications.
      6. Add replacement aircraft to air formations.
      7. Create ground unit replacement sub-units.
      8. Perform Aircraft Unit Upgrades.
      9. Perform Ground Unit weapon Upgrades.

15.2 NAVAL SUPPLY
Ships fire one round per weapon per round of combat. Once ammunition is expended, ships
can replenish their ammunition at ports.
Ports: Ports have an ability to rearm Naval vessels, depending on their size, and the availability
of sufficient supply at the port. Ports have Rearm points and expend those points on the basis
of the “Load Cost” of the weapons desiring rearming. If a Port has sufficient Rearm points
available for the weapons desiring rearming, those weapons will receive a suitable load of
ammunition. The supplies expended are based on the amount of ammo needed to replenish
the ship and the type of ammo needed.

15.3 GROUND UNIT SUPPLY
When tracing a supply path for movement of ground units or overland movement of supplies,
a supply value is generated. This is determined by tracing a path from the base transferring



                                                                                    Logistics

supplies or the ground unit moving to the destination. This supply value determines whether
the move is legal, and how much of the supplies are used up during the move.
To order a ground unit move to a specific hex, the path of the move must generate a positive
supply value to constitute a valid supply path. Ground units will move along a path that provides
the best possible supply route from their current hex to their destination. For automatic supply
movement, the supply value must be greater than 0. The greater the supply value, the more
often supplies will be moved and the less supplies will be expended during the move.

15.3.1 SUPPLY/FATIGUE EFFECTS ON LAND UNITS
Defensive and offensive fire of land units low on supplies will be reduced. Once a unit has less
supplies than its reported supply need, it stands a chance of having its combat fire reduced.
Once totally out of supplies, it will eventually have its fire greatly reduced. Ground units will
gain fatigue every turn. More fatigue will be suffered by troops that are marching or in combat.
Each turn, units will attempt to reduce their accumulated fatigue. The following items impact
the amount of fatigue reduced:
     »» The amount of support available in the hex versus the support required by the
        units in the hex. Units that are in hexes that have support available that equal
        or exceed the support required for that hex will reduce the greatest amount of
        fatigue. The less support available, the less fatigue is reduced. If a land unit has
        sufficient innate support, its Support value is shown in white; if it does not have
        enough, but it is in a friendly base hex that has enough total support located in
        hex, it is shown in green. If neither unit nor hex has enough, it is shown in red.
     »» Whether the unit is in a temperate or non-winter cold zone.
        Units in these hexes will reduce the most fatigue.
     »» Whether the unit is occupying a base, and the size of the base. Units
        occupying a base will reduce more fatigue. The larger the base
        (airfield size plus port size) the greater the fatigue reduction.
     »» The supply level of the unit. A unit that has supplies equal to or greater
        than its supply need will reduce more fatigue. The less supplies
        the unit has below its needs, the less the fatigue reduction.
When a unit’s fatigue level gets high, elements of the unit will slowly become disabled. When
a unit has more disabled elements than non-disabled, it will begin to have elements destroyed
instead of just disabled due to high fatigue.
Ground units with a Fatigue of less than 50 will gain 1 extra Fatigue per turn if at sea on a
transport. If 50 Fatigue is reached in this manner, their Fatigue will not increase beyond this
level.




15.4 AIR UNIT SUPPLY
Aircraft in an air unit can be in one of three states:
     »» Serviceable (can fly)
     »» Maintenance/Damaged (un-serviceable, unable to be flown)
     »» In Reserve
Ready aircraft are those aircraft that are capable of flying during the next day. Aircraft being
repaired and in reserve are not available to participate in Missions. Aircraft require aviation
support and supplies to remain ready, or to be repaired or activated from reserve. An aircraft
that is ready may become damaged due to combat or operational losses from flying (even
during Transfer Missions).
One Aviation Support point is required for each aircraft operating at an airbase for those aircraft
to function at maximum efficiency.
A base must have supplies equal to its stated supply needs for the aircraft operating at the
airfield to function at maximum efficiency (exception: level bombers require their base to
have supplies equal to double the supply need in order for the bombers to operate at max
efficiency).
Planes other than level bombers flying an Offensive Mission and planes flying an Escort
Mission expend one supply point per plane per Mission. Level bombers flying an offensive
Mission expend supplies equal to their Maximum Load divided by 1000 per Mission. All planes
flying other Mission types (search, CAP) expend 1/3 of a supply point per plane per Mission.
These supply points must be available for expenditure or the planes will not fly.
All aircraft groups require that their base contain supplies at least equal to the supply needs
for the base, or the group will not fly more than 75% of the ready aircraft in the group on an
Offensive or Escort Mission.
Level bomber squadrons require that their base contain supplies at least double the supply
needs for the base, or the level bomber group will not fly more than 75% of the ready aircraft
in the group on an Offensive Mission.
All groups attempting to fly any other Mission type (Naval Search, CAP, etc.) require that their
base contain supplies at least one half (50%) the supply needs for the base or the group will
not fly more than 75% of the ready aircraft in the group.

15.4.1 AIRCRAFT STATUS
During the Supply Operations Phase each day there is a chance that aircraft will change
their state. An aircraft that is ready may become damaged because the base lacks sufficient
aviation support and supplies. The chance of a plane being repaired is based on the damage to


                                                                                      Logistics

its airfield’s service facility, the amount of aviation support available and the supplies available
at the base. Planes may also be placed in reserve due to insufficient supplies and/or aviation
support. A unit can never have more than its maximum ready aircraft ready at one time, with
any remaining planes being placed in reserve. Once the number of ready planes falls below the
unit’s maximum, the unit will attempt to move reserve aircraft to ready, but this will be based
on the aviation support and supplies available at the base.

15.4.1.2 AIRCRAFT STATUS ON SHIPS
Aircraft on ships are assumed to have sufficient aviation support and supplies. However:
     »» Planes on a ship may not fly if the ship’s combined System Damage and
        Floatation Damage are greater than 50. They may transfer off the ship if
        docked or at anchor at a base with an airfield with a size of at least 1 (they
        are assumed to have been manually unloaded and taken to the airfield).
     »» If the number of aircraft on board exceeds 115% of the
        ship’s capacity, only Transfer Missions can be flown.
     »» Planes won’t make an emergency landing (refer to 7.0.1.1.1.1
        Emergency Landings) on another Carrier in such a way as to
        cause it to exceed 110% of the carriers aircraft capacity.
     »» A ship may never have more aircraft on board than twice its capacity.

15.5 AUTOMATIC CONVOYS
By using the Automatic Convoys system, players can select certain ship types (AK’s, TK’s, and
certain escort supply ships) to be placed into a computer controlled system that will attempt
to keep bases supplied with needed supplies and fuel, and for the Japanese, will attempt to
pick up resources and oil to return them to Japan for production. Ships are put into this system
by the player at Osaka, San Francisco, or Karachi, and bases must be specifically set to be
included in the system to receive supplies/fuel or have resources picked up (do this by pressing
on the Auto Convoy System button at the top of the main game screen; bases may also be
added into the Auto Convoy system from the Base orders screen).

15.6 CAPTURING BASE RESOURCES
A base that generates a daily allotment of supplies, fuel, oil and/or resources will not generate
these items if the nationality of the base is not part of the side that controls the base.
Example: Chungking is nationality Chinese and has a daily allotment of supplies. If Chungking
is controlled by the Japanese player, no daily supplies will be generated. If the Allies recapture
Chungking, daily supplies will be generated. Players using the editor should be aware that if



a scenario is created with a base having a nationality that does not belong to the controlling
player, the daily allotments will not arrive unless the base is captured by the other side.

15.7 SPOILAGE
Spoilage (or waste) of fuel and supplies at a base may occur, based on the size of the base. To
determine this possibility, first add the port and airfield sizes. Any base with combined port and
airfield of 10 or more has no spoilage. Otherwise:
     »» Fuel over 1000 + ( ( port + airfield size ) * ( port +
        airfield size ) *2000 ) suffers spoilage.
     »» Supplies over 5000 + ( ( port + airfield size ) * ( port
        + airfield size ) * 3000 ) suffers spoilage.

15.8 BURMA ROAD
For the Allies, if a rail/road/trail path free of Japanese units between Tsuyung and Ledo or
between Tsuyung and Rangoon can be traced, than each day, 500 supply points per turn are
added to Tsuyung.
