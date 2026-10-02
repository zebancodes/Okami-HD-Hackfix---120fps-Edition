stock | All four submodels' E0/108 approaches use the globally time-corrected 2DA510 helper; the stored results need no additional division. | 317684 3176DA 317730 317786
stock | Shared actor heading approaches through the globally corrected 2DA510 turn helper. | 30493A
once | E37 advances from one to two after heading alignment, or from two to three after reaching the target; the selected branch is no longer active on the next update. | 30D582
stock | Newly spawned effect positioning computes target minus old position plus old position in each component, producing the player's submodel position rather than integrating a repeated step. | 2F7A0E 2F7A35 2F7A60
stock | Initialization resets +1312 and counts four fixed save-data flags once, then selects E34=0x105; this is a bit population count, not a duration. | 33057D 330596 3305AF
stock | Resource list construction traverses bounded 0xB0-byte records and adds distinct 0x400/0x600/0x800 namespace tags while linking their lists. | 3EDD54 3EDDD4 3EDE54
stock | Reward accounting records one defeated-actor ID and adds its two data-table reward values per 403AF0 notification from 239810; these are event totals rather than elapsed time. | 3F6875 3F68B7 3F68BE
once | Page-transition entry changes +A9 from zero to one before selecting the adjacent page index; +AC decrements exactly once during that entry. | 40CD48
stock | Menu +32 is the bounded row selection changed by directional command bits at B6AD20; its increment and decrement select records and refresh layout data. | 432C06 432CAB
once | Menu +33 advances zero to one after its asynchronous request completes, then one to two after constructing the screen; subsequent updates select case two. | 432F19 432F41
stock | Confirmation menu +6 is a bounded selection index changed by directional command bits at B6AD58, with explicit two- or three-choice wrapping. | 438367 438551
stock | Quantity selector +86 changes on directional command bits at B6AD58: one item or ten bounded item operations per command, followed by price and quantity display. It is not an elapsed-frame counter. | 441626 4416C3 441781 4418E2
