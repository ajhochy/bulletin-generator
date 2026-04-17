// Template gallery and designer

let _templatesInitialized = false;
let _pendingTemplateApply = null;
let _pendingApplyExitAfterChoice = false;
let _editingTemplate = null;
let _editingSavedSnapshot = '';
let _selectedZoneId = '';
let _selectedElement = null;
let _designerRenderTimer = null;
let _designerDrag = null;
let _designerFonts = [];
let _installedFonts = [];

const TEMPLATE_BINDINGS = ['cover', 'announcements', 'pco_items', 'calendar', 'serving_schedule', 'staff'];
const PCO_TYPES = ['song', 'liturgy', 'section', 'label'];
const DESIGNER_FONTS = [
  // System / generic
  'system-ui',
  'Georgia',
  // Google Fonts — sans-serif
  'Archivo Narrow',
  'Barlow Condensed',
  'Bricolage Grotesque',
  'DM Sans',
  'Figtree',
  'Fira Sans',
  'Funnel Sans',
  'IBM Plex Sans',
  'Inter',
  'Inter Tight',
  'Instrument Sans',
  'Libre Franklin',
  'Manrope',
  'Montserrat',
  'Open Sans',
  'Outfit',
  'Poppins',
  'Public Sans',
  'Raleway',
  'Red Hat Display',
  'Sora',
  'Space Grotesk',
  'Special Gothic',
  'Syne',
  'Unbounded',
  'Urbanist',
  'Work Sans',
  // Google Fonts — serif
  'Bree Serif',
  'BioRhyme',
  'DM Serif Text',
  'EB Garamond',
  'Eczar',
  'Fraunces',
  'Inknut Antiqua',
  'Instrument Serif',
  'Libre Baskerville',
  'Lora',
  'Marcellus',
  'Merriweather',
  'Neuton',
  'Newsreader',
  'Playfair Display',
  // Google Fonts — mono
  'DM Mono',
  'Geist Mono',
  'Noto Sans Mono',
  'Space Mono',
];
_designerFonts = DESIGNER_FONTS.slice();

const _GOOGLE_FONT_NAMES = [
  'Archivo Narrow','Barlow Condensed','Bricolage Grotesque','DM Sans','Figtree',
  'Fira Sans','Funnel Sans','IBM Plex Sans','Inter','Inter Tight','Instrument Sans',
  'Libre Franklin','Manrope','Montserrat','Open Sans','Outfit','Poppins',
  'Public Sans','Raleway','Red Hat Display','Sora','Space Grotesk','Special Gothic',
  'Syne','Unbounded','Urbanist','Work Sans',
  'Bree Serif','BioRhyme','DM Serif Text','EB Garamond','Eczar','Fraunces',
  'Inknut Antiqua','Instrument Serif','Libre Baskerville','Lora','Marcellus',
  'Merriweather','Neuton','Newsreader','Playfair Display',
  'DM Mono','Geist Mono','Noto Sans Mono','Space Mono',
];

function _injectGoogleFonts() {
  if (document.getElementById('tpl-google-fonts-link')) return;
  const families = _GOOGLE_FONT_NAMES
    .map(f => `family=${encodeURIComponent(f)}:ital,wght@0,400;0,600;0,700;1,400`)
    .join('&');
  const link = document.createElement('link');
  link.id = 'tpl-google-fonts-link';
  link.rel = 'stylesheet';
  link.href = `https://fonts.googleapis.com/css2?${families}&display=swap`;
  document.head.appendChild(link);
}

// Hardwired sample project used by the template designer canvas so it always
// shows realistic content regardless of what's loaded in the bulletin editor.
const DESIGNER_SAMPLE_STATE = {"svcTitle":"The Problem - 1 Cor. 1.10-2.16","svcDate":"April 19, 2026","svcChurch":"Visalia Christian Reformed Church","optCover":true,"optFooter":false,"optCal":true,"optBookletSize":"auto","optAnnouncements":true,"optVolunteers":true,"optStaff":true,"welcomeHeading":"","welcomeItems":["Nursery (0–2 yrs) is available off the NE corner of the courtyard.","Mother/Infant Room is available off the foyer with a live feed of the service.","Nursing Mothers with Toddlers Room is available and located next to the nursery.","Family Room is located off the foyer with books/toys for toddlers and preschoolers. Live feed of the service is available."],"announcements":[{"title":"","body":"**Grill Master's Challenge**, May 3rd. If you'd like to compete as a griller/team or if you'd like to sponsor a team, reach out to Tim Wolff. All proceeds from GMC go to supporting the summer ministries of VCRC Youth.","url":"","_breakBefore":false,"_noBreakBefore":false},{"title":"","body":"**CVC Annual Society Meeting**. Members in good standing of Visalia CRC are society members of Central Valley Christian Schools and are invited to the Society Meeting on Tuesday, April 28th at 7:00 PM in the HS Chapel/Auditorium. All are also invited to a retirement reception honoring Mr. Tim Kornelis from 5:45 - 6:45 PM in the courtyard outside the HS chapel before the meeting.","url":"","_breakBefore":false,"_noBreakBefore":false},{"title":"","body":"**VBS Amazon Wishlist:** Help us prepare for VBS! We've created an Amazon Wishlist with needed supplies. Whether big or small, every donation helps us share the love of Jesus with kids. View the list by scanning the QR code. Thank you for your support!","url":"https://www.amazon.com/hz/wishlist/ls/2WIGJXF265NPE?ref_=wl_share","_breakBefore":false,"_noBreakBefore":false},{"title":"","body":"**Vacation Bible School June 15–19** |VBS is coming soon. We're looking for volunteers to serve in a variety of areas.  If you'd like to get involved, contact Grace at 559-960-7926. ","url":"","_breakBefore":false,"_noBreakBefore":false},{"title":"","body":"**Camp Jubilee Camper Registration** is open at campjubilee.org. Join us for another amazing week of camp from May 31-June 5. Jubilee is open to all students from incoming 7th graders to graduating 8th graders. For more info, see Tim Wolff.","url":"campjubilee.org","_breakBefore":false,"_noBreakBefore":false},{"title":"","body":"**Women of Grace is offering a Bible Basics: The Storyline of Scripture** this summer (June - August). Are you new to the Bible and don't know where to start?  Do you wonder how the stories, characters, and timelines fit together? Then this study is for you! Please contact Anneke de Jong at 559-647-5343, if you're interested. Dates and times to be determined, based on participants.","url":"","_breakBefore":false,"_noBreakBefore":false}],"items":[{"type":"section","title":"PRELUDE","detail":"","_collapsed":true},{"type":"section","title":"GATHERING","detail":"","_collapsed":true},{"type":"label","title":"Welcome/Announcements","detail":"","_collapsed":true},{"type":"label","title":"Greeting from God/Mutual Greeting","detail":"","_collapsed":true},{"type":"label","title":"Call to Worship","detail":"Leader: 1 How lovely is your dwelling place, Lord Almighty!\nALL: 2 My soul yearns, even faints, for the courts of the Lord; my heart and my flesh cry out for the living God.\nLeader: 4 Blessed are those who dwell in your house;\nALL: they are ever praising you.\n-Psalm 84:1,2,4","_collapsed":true},{"type":"song","title":"Rise With The Sun","detail":"1 There's a song that's sung through the nations\nOf joyful thanks to the King\nWhere the countless saints who are rescued\nPraise Jesus who set them all free\n2 Hear the anthem sung in the islands\nWhere sun first touches the earth\nOver land and sea it advances\nNow joined by the saints of this church\nChorus\nRise with the sun lift up His name\nAll through the earth we sing out His praise\nEast to the west night to the day join in the song\nAnd sing out His praise\n3 I will add my voice to the chorus\nOf many people and tongues\nFor we share the gift of salvation\nAnd share in the life yet to come\nBridge\nAnd the church will sing holy holy, Holy are You Lord\nYou're the glorious One, We lift up Your name\n\nAnd the church will sing, Tabu *(Fijian)* Heilig *(German)*\nOli *(Australian Creole)* Are You Lord\nYou're the Lamb who was slain, We lift up Your name\n\nAnd the church will sing Shèngjié (Mandarin)\nSanto (Spanish) Kadosh (Hebrew) Are You Lord\nYou're the King who was raised, We lift up Your name\n\nAnd the church will sing holy holy, Holy are You Lord\nNow You reign evermore, We lift up Your name\nOver all of the world, We lift up Your name\n\n© 2025 CityAlight Music","_collapsed":true},{"type":"song","title":"Praise To The Lord The Almighty","detail":"1 Praise to the Lord the Almighty, the King of creation!\nO my soul, praise Him, for He is your health and salvation!\nCome all who hear; brothers and sisters, draw near,\nJoin me in glad adoration!\n2 Praise to the Lord , who over all things is wondrously reigning,\nShelt-ring you under His wings, oh, so gently sustaining.\nHave you not seen all that is needful has been\nSent by his gracious ordaining?\n3 Praise to the Lord, who will prosper your work and defend you;\nSurely His goodness and mercy shall daily attend you.\nPonder anew what the Almighty can do \nas with His love He befriends you.\n4 Praise to the Lord! O let all that is in me adore Him!\nAll that has life and breath Come now with praises before Him\nLet the amen sound from His people again \nGladly for all we adore Him\n\n\nCCLI Song #43073 Catherine Winkworth, Joachim Neander","_collapsed":true},{"type":"section","title":"CONFESSION","detail":"","_collapsed":true},{"type":"label","title":"Prayer","detail":"Leader: God of grace, we grieve that the church,\nwhich shares one Spirit, one faith, one hope, and one calling,\nhas become a broken communion in a broken world.\nThe one body spans all time, place, race, and language,\nbut in our fear we have fled from and fought one another,\nand in our pride we have mistaken our part for the whole.\nYet we marvel that you gather the pieces to do your work,\nthat you bless us with joy, with growth, and with signs of unity.\nForgive our sins and help us to commit ourselves\nto seeking and showing the unity of the body of Christ.\nIn his name, Amen.\n—based on Our World Belongs to God, Art. 43","_collapsed":true,"_fmt":{"bodySize":"sm"}},{"type":"section","title":"ASSURANCE","detail":"","_collapsed":true},{"type":"label","title":"based on Ephesians 2:14-18, NRSV","detail":"Leader: Jesus Christ is our peace;\nin his flesh he has broken down the dividing wall,\nthat is, the hostility between us.\nHe has abolished the law with its commandments and ordinances,\nthat he might create in himself one new humanity\nin place of the two, thus making peace,\nand might reconcile both groups to God\nin one body through the cross,\nthus putting to death that hostility through it.\nSo he came and proclaimed peace to you who were far off\nand peace to those who were near;\nfor through him both of us have access in one Spirit to the Father.\n—based on Ephesians 2:14-18, NRSV","_collapsed":true,"_fmt":{"bodySize":"sm"}},{"type":"label","title":"Passing the Peace","detail":"Leader: Christ is the sure source of our peace.\nMay Christ's peace be always with you.\nALL: And also with you.","_collapsed":true},{"type":"song","title":"You Are Holy (Prince Of Peace)","detail":"Verse\nYou are holy (You are holy), You are mighty (You are mighty)\nYou are worthy (You are worthy)\nWorthy of praise (worthy of praise)\nI will follow (I will follow), I will listen (I will listen)\nI will love You (I will love You), All of my days (all of my days)\nChorus 1\nI will sing to and worship, The King who is worthy\nAnd I will love and adore Him, And I will bow down before Him\nAnd I will sing to and worship, The King who is worthy\nAnd I will love and adore Him, And I will bow down before Him\nYou're my Prince of Peace, And I will live my life for You\nChorus 2\nYou are Lord of lords You are King of kings\nYou are mighty God Lord of ev'rything\nYou're Emmanuel You're the Great I Am\nYou're the Prince of Peace who is the Lamb\nYou're the living God You're my saving grace\nYou will reign forever You are Ancient of Days\nYou are Alpha Omega Beginning and End\nYou're my Savior Messiah Redeemer and Friend\nYou're my Prince of Peace, And I will live my life for You\nEnding\nYou're my Prince of Peace\nAnd I will live my life for You\n\n\nCCLI Song #2332149 © 1994 Imboden Music; Martha Jo Publishing Marc Imboden, Tammi Rhoton For use solely with the SongSelect® Terms of Use. All rights reserved. www.ccli.com","_collapsed":true},{"type":"label","title":"Apostle's Creed","detail":"","_collapsed":true},{"type":"section","title":"OFFERING","detail":"**Youth for Christ** a local mission outreach to teenagers extending the hope of life here and for eternity through Jesus Christ.\nNext week's offering is for **Faith Promise**","_collapsed":true,"_fmt":{"titleItalic":false,"titleAlign":"left","bodyAlign":"center"}},{"type":"label","title":"Deacon Prayer","detail":"","_collapsed":true},{"type":"label","title":"Offertory - Questions From Kids","detail":"","_collapsed":true},{"type":"section","title":"CHILDREN DISMISSED (AGES 3-K)","detail":"","_collapsed":true},{"type":"page-break","title":"","detail":"","_collapsed":true},{"type":"section","title":"CONGREGATIONAL PRAYER","detail":"","_collapsed":true},{"type":"section","title":"WORD","detail":"","_collapsed":true},{"type":"label","title":"Sermon - The Problem","detail":"10 I appeal to you, brothers and sisters, in the name of our Lord Jesus Christ, that all of you agree with one another in what you say and that there be no divisions among you, but that you be perfectly united in mind and thought. 11 My brothers and sisters, some from Chloe's household have informed me that there are quarrels among you. 12 What I mean is this: One of you says, \"I follow Paul\"; another, \"I follow Apollos\"; another, \"I follow Cephas\"; still another, \"I follow Christ.\"\n\n13 Is Christ divided? Was Paul crucified for you? Were you baptized in the name of Paul? 14 I thank God that I did not baptize any of you except Crispus and Gaius, 15 so no one can say that you were baptized in my name. 16 (Yes, I also baptized the household of Stephanas; beyond that, I don't remember if I baptized anyone else.) 17 For Christ did not send me to baptize, but to preach the gospel—not with wisdom and eloquence, lest the cross of Christ be emptied of its power.\n\n18 For the message of the cross is foolishness to those who are perishing, but to us who are being saved it is the power of God. 19 For it is written:\n\n\"I will destroy the wisdom of the wise; the intelligence of the intelligent I will frustrate.\"\n\n20 Where is the wise person? Where is the teacher of the law? Where is the philosopher of this age? Has not God made foolish the wisdom of the world? 21 For since in the wisdom of God the world through its wisdom did not know him, God was pleased through the foolishness of what was preached to save those who believe. 22 Jews demand signs and Greeks look for wisdom, 23 but we preach Christ crucified: a stumbling block to Jews and foolishness to Gentiles, 24 but to those whom God has called, both Jews and Greeks, Christ the power of God and the wisdom of God. 25 For the foolishness of God is wiser than human wisdom, and the weakness of God is stronger than human strength.\n\n26 Brothers and sisters, think of what you were when you were called. Not many of you were wise by human standards; not many were influential; not many were of noble birth. 27 But God chose the foolish things of the world to shame the wise; God chose the weak things of the world to shame the strong. 28 God chose the lowly things of this world and the despised things—and the things that are not—to nullify the things that are, 29 so that no one may boast before him. 30 It is because of him that you are in Christ Jesus, who has become for us wisdom from God—that is, our righteousness, holiness and redemption. 31 Therefore, as it is written: \"Let the one who boasts boast in the Lord.\"\n\n2 And so it was with me, brothers and sisters. When I came to you, I did not come with eloquence or human wisdom as I proclaimed to you the testimony about God. 2 For I resolved to know nothing while I was with you except Jesus Christ and him crucified. 3 I came to you in weakness with great fear and trembling. 4 My message and my preaching were not with wise and persuasive words, but with a demonstration of the Spirit's power, 5 so that your faith might not rest on human wisdom, but on God's power.\n\nGod's Wisdom Revealed by the Spirit\n6 We do, however, speak a message of wisdom among the mature, but not the wisdom of this age or of the rulers of this age, who are coming to nothing. 7 No, we declare God's wisdom, a mystery that has been hidden and that God destined for our glory before time began. 8 None of the rulers of this age understood it, for if they had, they would not have crucified the Lord of glory. 9 However, as it is written:\n\n\"What no eye has seen, what no ear has heard, and what no human mind has conceived\"—\n    the things God has prepared for those who love him—\n\n10 these are the things God has revealed to us by his Spirit.\n\nThe Spirit searches all things, even the deep things of God. 11 For who knows a person's thoughts except their own spirit within them? In the same way no one knows the thoughts of God except the Spirit of God. 12 What we have received is not the spirit of the world, but the Spirit who is from God, so that we may understand what God has freely given us. 13 This is what we speak, not in words taught us by human wisdom but in words taught by the Spirit, explaining spiritual realities with Spirit-taught words. 14 The person without the Spirit does not accept the things that come from the Spirit of God but considers them foolishness, and cannot understand them because they are discerned only through the Spirit. 15 The person with the Spirit makes judgments about all things, but such a person is not subject to merely human judgments, 16 for,\n\n\"Who has known the mind of the Lord so as to instruct him?\"\n\nBut we have the mind of Christ.\n-1 Cor. 1.10-2.16, Pastor Austin Kammeraad\n"},{"type":"section","title":"COMMUNION","detail":"","_collapsed":true},{"type":"song","title":"Rock Of Ages","detail":"1 Rock of Ages cleft for me, let me hide myself in thee\nLet the water and the blood from thy wounded side which flowed\nBe of sin the double cure, save from wrath and make me pure\n2 Not the labors of my hands can fulfill thy law's demands\nCould my zeal no respite know, could my tears forever flow\nAll for sin could not atone Thou must save and thou alone\n3 Nothing in my hand I bring, simply to the cross I cling\nNaked come to thee for dress, helpless look to thee for grace\nFoul I to the fountain fly Wash me Savior or I die\n\n\nCCLI Song #40588, Augustus Montague Toplady, Thomas Hastings","_collapsed":true},{"type":"song","title":"There Is A Redeemer","detail":"Verse 1\nThere is a Redeemer Jesus God's own Son\nPrecious Lamb of God Messiah Holy One\nChorus\nThank You O my Father, For giving us Your Son\nAnd leaving Your Spirit, Till the work on earth is done\nVerse 2\nJesus my Redeemer name above all names\nPrecious Lamb of God Messiah, O for sinners slain\nVerse 3\nWhen I stand in glory I will see His face\nThere I'll serve my King forever, In that holy place\n\nCCLI Song # 11483 Melody Green © 1982 Universal Music - Brentwood Benson Publishing (Admin. by Brentwood-Benson Music Publishing, Inc.) Birdwing Music (Admin. by Capitol CMG Publishing) Ears To Hear (Admin. by Capitol CMG Publishing) For use solely with the SongSelect® Terms of Use. All rights reserved. www.ccli.com CCLI License # 546549","_collapsed":true},{"type":"section","title":"SENDING","detail":"","_collapsed":true},{"type":"song","title":"Praise God From Whom All Blessings Flow","detail":"Praise God, from whom all blessings flow;\npraise him, all creatures here below;\npraise him above, ye heavenly host;\npraise Father, Son, and Holy Ghost. Amen.","_collapsed":true},{"type":"label","title":"Benediction","detail":"","_collapsed":true},{"type":"section","title":"SERMON NOTES","detail":"","_collapsed":true}],"giveOnlineUrl":"https://visaliacrc.churchcenter.com/giving","servingSchedule":{"weeks":[{"date":"April 19, 2026","planId":"82380553","teams":[{"name":"Audio/Visual","serviceTime":"8:00a","positions":[{"role":"SLIDES","names":["Kyle Tos"]},{"role":"VIDEO MIXER","names":["Tim Wolff"]},{"role":"SOUND","names":["Samuel Davis"]},{"role":"BROADCAST AUDIO","names":["Tracy Carney"]}]},{"name":"Vocals","serviceTime":"8:00a","positions":[{"role":"MALE SINGER","names":["Alexander Prins","Nathan Scheele","Jeremy Van Nieuwenhuyzen"]},{"role":"FEMALE MELODY","names":["Kennedy Bosma"]},{"role":"LITURGIST","names":["Alison Renkema"]}]},{"name":"Band","serviceTime":"8:00a","positions":[{"role":"DRUMS","names":["Trey Koetsier"]},{"role":"KEYS","names":["Shelly Weststeyn"]},{"role":"BASS GUITAR","names":["Michael Kornelis"]},{"role":"ACOUSTIC GUITAR","names":["AJ Hochhalter","Nathan Scheele"]},{"role":"PIANO","names":["Chris Harrison"]},{"role":"ELECTRIC GUITAR","names":["Jeremy Cozakas"]}]},{"name":"First Impression","serviceTime":"8:00a","positions":[{"role":"USHER","names":["Geostan Duffin","Bert de Jong","Gordon Atsma"]},{"role":"GREETER","names":["Eddie & Jessica Veenendaal"]},{"role":"INFO BOOTH","names":["Roger & Darlene Wigboldy"]},{"role":"COFFEE SERVER","names":["John & Leslie Ritzema"]}]},{"name":"Nursery","serviceTime":"8:00a","positions":[{"role":"NURSERY STAFF","names":["Caitlin Hamar","Cynthia Majors"]},{"role":"NURSERY- YOUTH VOLUNTEER","names":["Camie Hamar","Ellie Glen"]},{"role":"NURSERY- ADULT VOLUNTEER","names":["Patricia Nolen","Robin Atsma"]}]},{"name":"Children's Worship","serviceTime":"8:00a","positions":[{"role":"CHILDREN'S WORSHIP- LEADER","names":["Lisa Glen","Michaela DeGroot"]},{"role":"CHILDREN'S WORSHIP-HELPERS","names":["Emma de Jong","Juliana Weaver","Bryn Atsma"]}]},{"name":"Welcome & Watch","serviceTime":"8:00a","positions":[{"role":"WELCOME & WATCH","names":["Tony DeGroot","Bill Lemstra"]}]},{"name":"Audio/Visual","serviceTime":"10:30a","positions":[{"role":"SLIDES","names":["Kyle Tos"]},{"role":"VIDEO MIXER","names":["Tim Wolff"]},{"role":"SOUND","names":["Samuel Davis"]},{"role":"BROADCAST AUDIO","names":["Tracy Carney"]}]},{"name":"Vocals","serviceTime":"10:30a","positions":[{"role":"MALE SINGER","names":["Alexander Prins","Nathan Scheele","Jeremy Van Nieuwenhuyzen"]},{"role":"FEMALE MELODY","names":["Kennedy Bosma"]},{"role":"LITURGIST","names":["Alison Renkema"]}]},{"name":"Band","serviceTime":"10:30a","positions":[{"role":"DRUMS","names":["Trey Koetsier"]},{"role":"KEYS","names":["Shelly Weststeyn"]},{"role":"BASS GUITAR","names":["Michael Kornelis"]},{"role":"ACOUSTIC GUITAR","names":["AJ Hochhalter","Nathan Scheele"]},{"role":"PIANO","names":["Chris Harrison"]},{"role":"ELECTRIC GUITAR","names":["Jeremy Cozakas"]}]},{"name":"Welcome & Watch","serviceTime":"10:30a","positions":[{"role":"WELCOME & WATCH","names":["Clint Walhof","Henry Weststeyn"]}]},{"name":"Nursery","serviceTime":"10:30a","positions":[{"role":"NURSERY STAFF","names":["Caitlin Hamar"]},{"role":"NURSERY- ADULT VOLUNTEER","names":["Paige Kroes"]},{"role":"NURSERY- YOUTH VOLUNTEER","names":["Aaliyah Renkema"]}]},{"name":"Children's Worship","serviceTime":"10:30a","positions":[{"role":"CHILDREN'S WORSHIP- LEADER","names":["Tena Ficher"]},{"role":"CHILDREN'S WORSHIP-HELPERS","names":["Hudson DeGroot","Jase DeGroot","Tanner Veenendaal"]}]},{"name":"First Impression","serviceTime":"10:30a","positions":[{"role":"GREETER","names":["Jay & Darlene te Velde"]},{"role":"INFO BOOTH","names":["Marlene Collins","Edie Carter"]},{"role":"USHER","names":["David DeGroot","Jay III te Velde","Mike Wallen"]},{"role":"COFFEE SERVER","names":["Gerrit & Judy Bothof"]}]}]},{"date":"April 26, 2026","planId":"82380554","teams":[{"name":"Band","serviceTime":"8:00a","positions":[{"role":"DRUMS","names":["Landen Forsyth"]},{"role":"ACOUSTIC GUITAR","names":["AJ Hochhalter"]},{"role":"PIANO","names":["John Singh"]},{"role":"BASS GUITAR","names":["Jeremy Cozakas"]}]},{"name":"Audio/Visual","serviceTime":"8:00a","positions":[{"role":"SLIDES","names":["David Verhoeven"]},{"role":"VIDEO MIXER","names":["Tim Wolff"]},{"role":"SOUND","names":["Tracy Carney"]},{"role":"BROADCAST AUDIO","names":["Samuel Davis"]}]},{"name":"Vocals","serviceTime":"8:00a","positions":[{"role":"FEMALE MELODY","names":["Sarena Sytsma"]},{"role":"LITURGIST","names":["Elizabeth Verhoeven"]},{"role":"MALE SINGER","names":["Tim Kornelis"]},{"role":"FEMALE HARMONY","names":["Kaitlyn Yocum"]}]},{"name":"Nursery","serviceTime":"8:00a","positions":[{"role":"NURSERY STAFF","names":["Julia Truesdell"]},{"role":"NURSERY- YOUTH VOLUNTEER","names":["Makenna DeGroff","Peyton Huntley"]},{"role":"NURSERY- ADULT VOLUNTEER","names":["Elise Monell","Ingrid Hamar","Taryn Rocha"]}]},{"name":"Children's Worship","serviceTime":"8:00a","positions":[{"role":"CHILDREN'S WORSHIP- LEADER","names":["Chelsea Leyendekker","Erin Schoneveld"]},{"role":"CHILDREN'S WORSHIP-HELPERS","names":["Elliott Leyendekker","Lucas Huntley","Luke DeGroff"]}]},{"name":"First Impression","serviceTime":"8:00a","positions":[{"role":"COFFEE SERVER","names":["Ron & Deb Kroonenberg"]},{"role":"INFO BOOTH","names":["Art & Michelle Leyendekker"]},{"role":"USHER","names":["Harm de Jong","Rick Schotanus","Tyler Grove"]}]},{"name":"Welcome & Watch","serviceTime":"8:00a","positions":[{"role":"WELCOME & WATCH","names":["Dustin Berlinger","Josh Witschi"]}]},{"name":"Band","serviceTime":"10:30a","positions":[{"role":"DRUMS","names":["Landen Forsyth"]},{"role":"ACOUSTIC GUITAR","names":["AJ Hochhalter"]},{"role":"PIANO","names":["John Singh"]},{"role":"BASS GUITAR","names":["Jeremy Cozakas"]}]},{"name":"Audio/Visual","serviceTime":"10:30a","positions":[{"role":"SLIDES","names":["David Verhoeven"]},{"role":"VIDEO MIXER","names":["Tim Wolff"]},{"role":"SOUND","names":["Tracy Carney"]},{"role":"BROADCAST AUDIO","names":["Samuel Davis"]}]},{"name":"Vocals","serviceTime":"10:30a","positions":[{"role":"FEMALE MELODY","names":["Sarena Sytsma"]},{"role":"LITURGIST","names":["Elizabeth Verhoeven"]},{"role":"MALE SINGER","names":["Tim Kornelis"]},{"role":"FEMALE HARMONY","names":["Kaitlyn Yocum"]}]},{"name":"Nursery","serviceTime":"10:30a","positions":[{"role":"NURSERY STAFF","names":["Julia Truesdell","Cynthia Majors"]},{"role":"NURSERY- YOUTH VOLUNTEER","names":["Leah Walhof"]}]},{"name":"Children's Worship","serviceTime":"10:30a","positions":[{"role":"CHILDREN'S WORSHIP- LEADER","names":["Cynthia Davis"]},{"role":"CHILDREN'S WORSHIP-HELPERS","names":["Riley Bosma","Willem Renkema"]}]},{"name":"First Impression","serviceTime":"10:30a","positions":[{"role":"COFFEE SERVER","names":["Eric & Lisa Beedle"]},{"role":"INFO BOOTH","names":["Greg & Joanne Groen"]},{"role":"USHER","names":["Aaron Van Dyk","Jack Bothof","Jared DeGroot"]}]},{"name":"Welcome & Watch","serviceTime":"10:30a","positions":[{"role":"WELCOME & WATCH","names":["Darin Vanden Berg","Jonathan Verhoeven"]}]}],"_breakBefore":true}]},"calEvents":[{"title":"Worship Service","start":{"iso":"2026-04-19T08:00:00-07:00","allDay":false},"end":{"iso":"2026-04-19T09:00:00-07:00","allDay":false},"location":"","description":"","_srcTitle":"Worship Service"},{"title":"Sunday School","start":{"iso":"2026-04-19T09:20:00-07:00","allDay":false},"end":{"iso":"2026-04-19T10:15:00-07:00","allDay":false},"location":"","description":"","_srcTitle":"Sunday School"},{"title":"Sunday School with Pastor Lambert","start":{"iso":"2026-04-19T09:30:00-07:00","allDay":false},"end":{"iso":"2026-04-19T10:15:00-07:00","allDay":false},"location":"Visalia CRC Chapel","description":"","_srcTitle":"Sunday School with Pastor Lambert"},{"title":"Worship Service","start":{"iso":"2026-04-19T10:30:00-07:00","allDay":false},"end":{"iso":"2026-04-19T11:30:00-07:00","allDay":false},"location":"","description":"","_srcTitle":"Worship Service"},{"title":"Youth Group - JH & HS","start":{"iso":"2026-04-22T18:45:00-07:00","allDay":false},"end":{"iso":"2026-04-22T20:30:00-07:00","allDay":false},"location":"Visalia Christian Reformed Church, 1030 S Linwood St, Visalia, CA 93277, USA","description":"","_srcTitle":"Youth Group - JH & HS"},{"title":"Worship Service-GEMS Sunday","start":{"iso":"2026-04-26T08:00:00-07:00","allDay":false},"end":{"iso":"2026-04-26T09:00:00-07:00","allDay":false},"location":"","description":"","_srcTitle":"Worship Service"},{"title":"Sunday School","start":{"iso":"2026-04-26T09:20:00-07:00","allDay":false},"end":{"iso":"2026-04-26T10:15:00-07:00","allDay":false},"location":"","description":"","_srcTitle":"Sunday School"},{"title":"Sunday School with Pastor Lambert","start":{"iso":"2026-04-26T09:30:00-07:00","allDay":false},"end":{"iso":"2026-04-26T10:15:00-07:00","allDay":false},"location":"Visalia CRC Chapel","description":"","_srcTitle":"Sunday School with Pastor Lambert"},{"title":"Worship Service-GEMS Sunday","start":{"iso":"2026-04-26T10:30:00-07:00","allDay":false},"end":{"iso":"2026-04-26T11:30:00-07:00","allDay":false},"location":"","description":"","_srcTitle":"Worship Service"}],"volTeamFilter":{},"breakBeforeCalendar":true,"breakBeforeStaff":false,"calBreakBeforeDates":[],"bottomMerge":{"oow":true,"serving":false,"calendar":false,"staff":false}};

// Temporarily swap all global state to the sample data, call fn(), then restore.
// Used by renderDesignerCanvas() so the designer always shows realistic content.
function _withDesignerSampleData(fn) {
  const d = DESIGNER_SAMPLE_STATE;
  const savedDom = {
    svcTitle: svcTitle.value,
    svcDate: svcDate.value,
    svcChurch: svcChurch.value,
    optCoverChecked: optCover.checked,
    optFooterChecked: optFooter.checked,
    optAnnouncementsChecked: optAnnouncements.checked,
    optCalChecked: optCal.checked,
    optVolunteersChecked: optVolunteers.checked,
    optStaffChecked: optStaff.checked,
    optBookletSizeVal: optBookletSize.value,
    itemListHTML: itemList.innerHTML,
  };
  const savedVars = { items, annData, calEvents, servingSchedule, coverImageUrl,
    bottomMerge, giveOnlineUrl, breakBeforeCalendar, breakBeforeStaff,
    calBreakBeforeDates, welcomeItems, welcomeHeading, volTeamFilter };

  svcTitle.value = d.svcTitle || '';
  svcDate.value = d.svcDate || '';
  svcChurch.value = d.svcChurch || '';
  optCover.checked = d.optCover !== false;
  optFooter.checked = !!d.optFooter;
  optAnnouncements.checked = d.optAnnouncements !== false;
  optCal.checked = d.optCal !== false;
  optVolunteers.checked = d.optVolunteers !== false;
  optStaff.checked = d.optStaff !== false;
  optBookletSize.value = d.optBookletSize || 'auto';
  itemList.innerHTML = ''; // prevent syncAllItems() from clobbering items
  items = d.items || [];
  annData = (d.announcements || []).map(a => ({ title: a.title || '', body: a.body || '', url: a.url || '', _breakBefore: !!a._breakBefore, _noBreakBefore: !!a._noBreakBefore }));
  calEvents = d.calEvents || [];
  servingSchedule = d.servingSchedule || null;
  coverImageUrl = null;
  bottomMerge = Object.assign({ oow: false, serving: false, calendar: false, staff: false }, d.bottomMerge);
  giveOnlineUrl = d.giveOnlineUrl || '';
  breakBeforeCalendar = !!d.breakBeforeCalendar;
  breakBeforeStaff = !!d.breakBeforeStaff;
  calBreakBeforeDates = d.calBreakBeforeDates || [];
  welcomeItems = d.welcomeItems || [];
  welcomeHeading = d.welcomeHeading || '';
  volTeamFilter = d.volTeamFilter || {};

  try {
    fn();
  } finally {
    svcTitle.value = savedDom.svcTitle;
    svcDate.value = savedDom.svcDate;
    svcChurch.value = savedDom.svcChurch;
    optCover.checked = savedDom.optCoverChecked;
    optFooter.checked = savedDom.optFooterChecked;
    optAnnouncements.checked = savedDom.optAnnouncementsChecked;
    optCal.checked = savedDom.optCalChecked;
    optVolunteers.checked = savedDom.optVolunteersChecked;
    optStaff.checked = savedDom.optStaffChecked;
    optBookletSize.value = savedDom.optBookletSizeVal;
    itemList.innerHTML = savedDom.itemListHTML;
    items = savedVars.items;
    annData = savedVars.annData;
    calEvents = savedVars.calEvents;
    servingSchedule = savedVars.servingSchedule;
    coverImageUrl = savedVars.coverImageUrl;
    bottomMerge = savedVars.bottomMerge;
    giveOnlineUrl = savedVars.giveOnlineUrl;
    breakBeforeCalendar = savedVars.breakBeforeCalendar;
    breakBeforeStaff = savedVars.breakBeforeStaff;
    calBreakBeforeDates = savedVars.calBreakBeforeDates;
    welcomeItems = savedVars.welcomeItems;
    welcomeHeading = savedVars.welcomeHeading;
    volTeamFilter = savedVars.volTeamFilter;
  }
}

// ─── In-app modal helper (replaces browser prompt()) ──────────────────────
// config: { title, confirmText?, fields: [{label, type, name, options?, value?, placeholder?}] }
// Returns Promise → { [name]: value } on confirm, null on cancel.
function tdShowModal(config) {
  return new Promise(resolve => {
    const backdrop = document.createElement('div');
    backdrop.className = 'td-modal-backdrop';

    const modal = document.createElement('div');
    modal.className = 'td-modal';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');

    const titleEl = document.createElement('div');
    titleEl.className = 'td-modal-title';
    titleEl.textContent = config.title || '';
    modal.appendChild(titleEl);

    const fieldEls = {};
    (config.fields || []).forEach(field => {
      const lbl = document.createElement('label');
      lbl.className = 'td-modal-field-label';
      lbl.textContent = field.label;
      modal.appendChild(lbl);

      let el;
      if (field.type === 'template-list') {
        el = document.createElement('div');
        el.className = 'td-modal-template-list';
        let selectedIdx = field.value != null ? field.value : 0;
        (field.options || []).forEach((opt, i) => {
          const btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'td-modal-template-option' + (i === selectedIdx ? ' selected' : '');
          btn.textContent = typeof opt === 'object' ? opt.label : opt;
          btn.addEventListener('click', () => {
            el.querySelectorAll('.td-modal-template-option').forEach(b => b.classList.remove('selected'));
            btn.classList.add('selected');
            selectedIdx = i;
          });
          btn.addEventListener('dblclick', () => { selectedIdx = i; finish(true); });
          el.appendChild(btn);
        });
        el._getValue = () => selectedIdx;
      } else if (field.type === 'select') {
        el = document.createElement('select');
        el.className = 'td-modal-select';
        (field.options || []).forEach(opt => {
          const o = document.createElement('option');
          o.value = typeof opt === 'object' ? opt.value : opt;
          o.textContent = typeof opt === 'object' ? opt.label : opt;
          el.appendChild(o);
        });
        if (field.value != null) el.value = field.value;
      } else {
        el = document.createElement('input');
        el.className = 'td-modal-input';
        el.type = field.type || 'text';
        el.value = field.value != null ? field.value : '';
        el.placeholder = field.placeholder || '';
      }
      modal.appendChild(el);
      fieldEls[field.name] = el;
    });

    const actions = document.createElement('div');
    actions.className = 'td-modal-actions';
    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'td-modal-btn td-modal-btn-cancel';
    cancelBtn.textContent = 'Cancel';
    cancelBtn.addEventListener('click', () => finish(false));
    actions.appendChild(cancelBtn);
    const confirmBtn = document.createElement('button');
    confirmBtn.type = 'button';
    confirmBtn.className = 'td-modal-btn td-modal-btn-primary';
    confirmBtn.textContent = config.confirmText || 'OK';
    confirmBtn.addEventListener('click', () => finish(true));
    actions.appendChild(confirmBtn);
    modal.appendChild(actions);

    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);

    const firstInput = modal.querySelector('input, select');
    if (firstInput) setTimeout(() => { firstInput.focus(); firstInput.select?.(); }, 40);

    const onKey = e => {
      if (e.key === 'Escape') finish(false);
      else if (e.key === 'Enter' && e.target.tagName !== 'BUTTON' && e.target.tagName !== 'SELECT') finish(true);
    };
    document.addEventListener('keydown', onKey);
    backdrop.addEventListener('click', e => { if (e.target === backdrop) finish(false); });

    function finish(confirmed) {
      document.removeEventListener('keydown', onKey);
      backdrop.remove();
      if (!confirmed) { resolve(null); return; }
      const values = {};
      Object.entries(fieldEls).forEach(([name, el]) => {
        values[name] = el._getValue ? el._getValue() : el.value;
      });
      resolve(values);
    }
  });
}

function cloneTemplate(template) {
  return JSON.parse(JSON.stringify(template || getClassicTemplateFallback()));
}

function templateSnapshot(template) {
  return JSON.stringify(template || {});
}

function designerIsDirty() {
  return !!_editingTemplate && templateSnapshot(_editingTemplate) !== _editingSavedSnapshot;
}

function getClassicTemplateFallback() {
  return {
    id: 'classic',
    name: 'Classic',
    builtIn: true,
    pageSize: '5.5x8.5',
    cssVars: {},
    typeFormats: {},
    zones: [
      { id: 'z-cover',   binding: 'cover',            order: 1, enabled: true, match: {}, elements: {} },
      { id: 'z-ann',     binding: 'announcements',    order: 2, enabled: true, match: {}, elements: {} },
      { id: 'z-oow',     binding: 'pco_items',        order: 3, enabled: true, match: {}, elements: {} },
      { id: 'z-cal',     binding: 'calendar',         order: 4, enabled: true, match: {}, elements: {} },
      { id: 'z-serving', binding: 'serving_schedule', order: 5, enabled: true, match: {}, elements: {} },
      { id: 'z-staff',   binding: 'staff',            order: 6, enabled: true, match: {}, elements: {} },
    ],
  };
}

function getTemplateList() {
  const list = Array.isArray(templates) && templates.length ? templates : [getClassicTemplateFallback()];
  if (list.some(t => t && t.id === 'classic')) return list;
  return [getClassicTemplateFallback()].concat(list);
}

function makeTemplateId() {
  return `tpl_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function templateSlug(value) {
  return String(value || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'template';
}

function makeZoneId(binding) {
  return `z-${binding.replace(/_/g, '-')}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
}

function deterministicZoneId(zone, index) {
  const m = zone.match || {};
  return [
    'z',
    zone.binding || 'zone',
    m.type || 'all',
    m.title || m.titleContains || '',
    index + 1,
  ].map(templateSlug).filter(Boolean).join('-');
}

function bindingLabel(binding) {
  return ({
    cover: 'Cover',
    announcements: 'Announcements',
    pco_items: 'Order of Worship',
    calendar: 'Calendar',
    serving_schedule: 'Serving',
    staff: 'Staff',
  })[binding] || binding || 'Rule';
}

function zoneLabel(zone) {
  if (!zone) return 'Rule';
  const m = zone.match || {};
  if (zone.binding === 'pco_items' && m.type) {
    const typeLabel = m.type.charAt(0).toUpperCase() + m.type.slice(1);
    if (m.title) return `${typeLabel}: "${m.title}"`;
    if (m.titleContains) return `${typeLabel}: contains "${m.titleContains}"`;
    return `${typeLabel} Items`;
  }
  return bindingLabel(zone.binding);
}

function zoneSpecificityText(zone) {
  if (!zone) return '';
  const m = zone.match || {};
  const binding = bindingLabel(zone.binding).toLowerCase();
  if (zone.binding !== 'pco_items') return `Applies to: all ${binding} content`;
  if (!m.type) return 'Applies to: all order of worship items';
  if (m.title) return `Applies to: ${m.type} items titled "${m.title}" exactly`;
  if (m.titleContains) return `Applies to: ${m.type} items containing "${m.titleContains}"`;
  return `Applies to: all ${m.type} items`;
}

function sortedZones() {
  return (_editingTemplate?.zones || [])
    .slice()
    .sort((a, b) => (a.order || 0) - (b.order || 0));
}

function templateDisplayOrder(template) {
  const zones = Array.isArray(template?.zones) ? template.zones : [];
  return zones
    .filter(z => z && z.enabled !== false)
    .slice()
    .sort((a, b) => (a.order || 0) - (b.order || 0));
}

function getZoneById(zoneId) {
  return (_editingTemplate?.zones || []).find(z => z.id === zoneId) || null;
}

function getSelectedZone() {
  return getZoneById(_selectedZoneId) || sortedZones()[0] || null;
}

function getZoneElements(zone) {
  if (!zone) return [];
  return getRegistryElements(zone.binding, zone.match?.type);
}

function getZoneElementFmt(zone, elementKey) {
  if (!zone) return {};
  if (!zone.elements || typeof zone.elements !== 'object') zone.elements = {};
  if (!zone.elements[elementKey] || typeof zone.elements[elementKey] !== 'object') zone.elements[elementKey] = {};
  return zone.elements[elementKey];
}

function readZoneElementFmt(zone, elementKey) {
  if (!zone || !zone.elements || typeof zone.elements !== 'object') return {};
  const fmt = zone.elements[elementKey];
  return fmt && typeof fmt === 'object' ? fmt : {};
}

function markDesignerDirty() {
  renderZoneTree();
  renderMatchEditor();
  renderDesignerToolbar();
  scheduleDesignerCanvasRender();
}

function designerFontOptions() {
  const names = new Set(_designerFonts.concat(_installedFonts.map(f => f.family)).concat([_editingTemplate?.cssVars?.fontFamily].filter(Boolean)));
  return Array.from(names).sort((a, b) => a.localeCompare(b)).map(name => ({
    value: name,
    label: _installedFonts.some(f => f.family === name) ? `${name} (Installed)` : name,
  }));
}

async function loadDesignerFonts() {
  _injectGoogleFonts();
  try {
    const data = await apiFetch('/api/fonts');
    _installedFonts = [].concat(data.user || [], data.cached || []);
    _installedFonts.forEach(font => {
      if (font.family) _designerFonts.push(font.family);
    });
    renderFontManager();
    renderDesignerToolbar();
  } catch (err) {
    // Font APIs are optional for older servers; keep local/system fonts available.
  }
  if (typeof window === 'undefined' || typeof window.queryLocalFonts !== 'function') return;
  try {
    const localFonts = await window.queryLocalFonts();
    const names = new Set(_designerFonts);
    localFonts.forEach(font => {
      if (font.family) names.add(font.family);
    });
    _designerFonts = Array.from(names);
    renderDesignerToolbar();
  } catch (err) {
    // Browsers may require permission for local font access; the curated list remains available.
  }
}

function showFontsModal() {
  const existing = document.getElementById('tpl-fonts-modal');
  if (existing) existing.remove();

  const backdrop = document.createElement('div');
  backdrop.id = 'tpl-fonts-modal';
  backdrop.style.cssText = 'position:fixed;inset:0;z-index:600;background:rgba(14,19,24,0.45);display:flex;align-items:center;justify-content:center;';

  const modal = document.createElement('div');
  modal.style.cssText = 'background:#fff;border-radius:10px;padding:20px;width:420px;max-width:95vw;max-height:80vh;display:flex;flex-direction:column;gap:12px;box-shadow:0 8px 40px rgba(0,0,0,0.18);';

  const header = document.createElement('div');
  header.style.cssText = 'display:flex;align-items:center;justify-content:space-between;';
  const title = document.createElement('div');
  title.style.cssText = 'font-size:15px;font-weight:700;';
  title.textContent = 'Custom Fonts';
  const closeBtn = document.createElement('button');
  closeBtn.type = 'button';
  closeBtn.className = 'btn btn-ghost btn-xs';
  closeBtn.textContent = '✕';
  closeBtn.addEventListener('click', () => backdrop.remove());
  header.appendChild(title);
  header.appendChild(closeBtn);
  modal.appendChild(header);

  const sub = document.createElement('div');
  sub.style.cssText = 'font-size:12px;color:#737373;';
  sub.textContent = 'Upload licensed TTF, OTF, WOFF, or WOFF2 files to use in template font pickers.';
  modal.appendChild(sub);

  const list = document.createElement('div');
  list.style.cssText = 'flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:6px;min-height:40px;';
  const userFonts = _installedFonts.filter(f => f.source === 'user');
  if (!userFonts.length) {
    const empty = document.createElement('div');
    empty.style.cssText = 'font-size:12px;color:#9ca3af;padding:8px 0;';
    empty.textContent = 'No uploaded fonts yet.';
    list.appendChild(empty);
  } else {
    userFonts.forEach(font => {
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:8px;border:1px solid #e5e7eb;border-radius:6px;padding:6px 10px;';
      const name = document.createElement('span');
      name.style.cssText = `font-size:14px;font-family:${font.family},sans-serif;`;
      name.textContent = font.family;
      row.appendChild(name);
      const del = document.createElement('button');
      del.type = 'button';
      del.className = 'btn btn-ghost btn-xs text-error';
      del.textContent = 'Delete';
      del.addEventListener('click', () => deleteUploadedFont(font).then(() => { backdrop.remove(); showFontsModal(); }));
      row.appendChild(del);
      list.appendChild(row);
    });
  }
  modal.appendChild(list);

  const uploadBtn = document.createElement('button');
  uploadBtn.type = 'button';
  uploadBtn.className = 'btn btn-ghost btn-sm';
  uploadBtn.textContent = 'Upload Font…';
  uploadBtn.addEventListener('click', () => document.getElementById('tpl-font-upload-input')?.click());
  modal.appendChild(uploadBtn);

  backdrop.addEventListener('click', e => { if (e.target === backdrop) backdrop.remove(); });
  backdrop.appendChild(modal);
  document.body.appendChild(backdrop);
}

function renderFontManager() {
  // Font list is now shown in the modal via showFontsModal(); nothing to render inline.
}

async function uploadFontFile(file) {
  if (!file) return;
  const form = new FormData();
  form.append('file', file);
  form.append('family', file.name.replace(/\.(ttf|otf|woff2?|TTF|OTF|WOFF2?)$/, '').replace(/[-_]+/g, ' '));
  try {
    const res = await fetch('/api/fonts', { method: 'POST', body: form });
    if (!res.ok) {
      let err = null;
      try { err = await res.json(); } catch (_) {}
      throw new Error(err?.error || `Font upload failed (${res.status})`);
    }
    setStatus(`Uploaded font "${file.name}".`, 'success');
    await loadDesignerFonts();
  } catch (err) {
    setStatus('Font upload failed: ' + (err.message || err), 'error');
  }
}

async function deleteUploadedFont(font) {
  if (!font || !confirm(`Delete uploaded font "${font.family}"?`)) return;
  try {
    await apiFetch(`/api/fonts/${encodeURIComponent(font.slug)}`, 'DELETE');
    setStatus(`Deleted "${font.family}".`, 'success');
    await loadDesignerFonts();
  } catch (err) {
    setStatus('Font delete failed: ' + (err.message || err), 'error');
  }
}

function normalizeTemplateForExport(template) {
  const copy = cloneTemplate(template);
  copy.id = templateSlug(copy.name || copy.id);
  copy.builtIn = false;
  copy.zones = (copy.zones || []).map((zone, index) => {
    const z = cloneTemplate(zone);
    z.id = deterministicZoneId(z, index);
    return z;
  });
  return copy;
}

function validateImportedTemplate(template) {
  if (!template || typeof template !== 'object' || Array.isArray(template)) return 'Template JSON must be an object.';
  if (!Array.isArray(template.zones) || !template.zones.length) return 'Template must include zones.';
  const validBindings = new Set(TEMPLATE_BINDINGS);
  for (const zone of template.zones) {
    if (!zone || typeof zone !== 'object') return 'Each zone must be an object.';
    if (!validBindings.has(zone.binding)) return `Invalid zone binding: ${zone.binding || '(missing)'}`;
    if (zone.elements && (typeof zone.elements !== 'object' || Array.isArray(zone.elements))) return 'Zone elements must be objects.';
  }
  return '';
}

function exportTemplate(template = _editingTemplate) {
  if (!template) return;
  const normalized = normalizeTemplateForExport(template);
  const blob = new Blob([JSON.stringify(normalized, null, 2) + '\n'], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${templateSlug(normalized.name || normalized.id)}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function importTemplateFile(file) {
  if (!file) return;
  try {
    const imported = JSON.parse(await file.text());
    const error = validateImportedTemplate(imported);
    if (error) throw new Error(error);
    const template = cloneTemplate(imported);
    template.name = String(template.name || 'Imported Template').trim();
    template.id = templateSlug(template.id || template.name);
    template.builtIn = false;
    const ids = new Set(getTemplateList().map(t => t.id));
    if (ids.has(template.id)) template.id = `${template.id}-${Date.now().toString(36)}`;
    template.zones = template.zones.map((zone, index) => Object.assign({}, zone, {
      id: zone.id || deterministicZoneId(zone, index),
      order: Number.isFinite(Number(zone.order)) ? Number(zone.order) : index + 1,
      enabled: zone.enabled !== false,
      match: zone.match && typeof zone.match === 'object' ? zone.match : {},
      elements: zone.elements && typeof zone.elements === 'object' ? zone.elements : {},
    }));
    await apiFetch('/api/templates', 'POST', template);
    setTemplates(templates.concat([template]));
    renderTemplateGallery();
    openTemplateDesigner(template);
    setStatus(`Imported "${template.name}".`, 'success');
  } catch (err) {
    setStatus('Template import failed: ' + (err.message || err), 'error');
  } finally {
    const input = document.getElementById('tpl-import-input');
    if (input) input.value = '';
  }
}

function renderTemplateThumb(template) {
  const wrap = document.createElement('div');
  wrap.className = 'tpl-thumb-wrap';
  return wrap;
}

function _fillGalleryThumbs(thumbMap) {
  if (!thumbMap.length) return;
  const previousTemplate = cloneTemplate(activeDocTemplate);
  thumbMap.forEach(({ wrap, template }) => {
    setActiveDocTemplate(template);
    applyDocTemplate();
    _withDesignerSampleData(() => renderPreview());

    // Show OOW page (page 3): skip cover + announcements (pages 1-2)
    const nonCoverPages = Array.from(previewPane.querySelectorAll('.booklet-page:not(.cover)'));
    const oowPage = nonCoverPages[1] || nonCoverPages[0] || previewPane.querySelector('.booklet-page');
    if (!oowPage) return;

    const pageW = oowPage.offsetWidth || 528;
    const pageH = oowPage.offsetHeight || 816;
    // Fill the card width; card min-width is 160px so use that as target
    const THUMB_W = 220;
    const scale   = THUMB_W / pageW;
    const thumbH  = Math.round(pageH * scale);

    const clone = oowPage.cloneNode(true);
    clone.querySelectorAll('.preview-page-num, .pg-break-ctrl, .pg-split-ctrl').forEach(el => el.remove());
    clone.style.cssText = `width:${pageW}px; transform:scale(${scale}); transform-origin:top left; pointer-events:none; flex-shrink:0;`;

    const scaler = document.createElement('div');
    scaler.style.cssText = `width:${THUMB_W}px; height:${thumbH}px; overflow:hidden;`;
    scaler.appendChild(clone);

    wrap.style.cssText = `width:100%; height:${thumbH}px; overflow:hidden; background:var(--base-200,#f3f4f6);`;
    wrap.appendChild(scaler);
  });
  setActiveDocTemplate(previousTemplate);
  applyDocTemplate();
  renderPreview();
}

function renderTemplateGallery() {
  initTemplateControls();
  const grid = document.getElementById('tpl-grid');
  if (!grid) return;
  grid.innerHTML = '';

  const thumbMap = [];

  getTemplateList().forEach(template => {
    const card = document.createElement('div');
    card.className = 'tpl-template-card';

    // Thumbnail (filled after all cards built)
    const wrap = renderTemplateThumb(template);
    thumbMap.push({ wrap, template });
    card.appendChild(wrap);

    // Info strip below preview
    const cv = template.cssVars || {};
    const info = document.createElement('div');
    info.className = 'tpl-card-info';

    // Name
    const name = document.createElement('div');
    name.style.cssText = 'font-size:12px; font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;';
    name.textContent = template.name || 'Untitled Template';
    info.appendChild(name);

    // Swatches + badges row
    const metaRow = document.createElement('div');
    metaRow.style.cssText = 'display:flex; align-items:center; gap:5px; margin-top:3px;';
    [cv.primary || '#111827', cv.muted || '#6b7280', cv.accent || '#172429', cv.border || '#e5e7eb'].forEach(c => {
      const sw = document.createElement('div');
      sw.style.cssText = `width:9px; height:9px; border-radius:50%; background:${c}; border:1px solid rgba(0,0,0,0.1); flex-shrink:0;`;
      sw.title = c;
      metaRow.appendChild(sw);
    });
    if (template.builtIn) {
      const b = document.createElement('span');
      b.className = 'tpl-template-badge tpl-badge-builtin';
      b.textContent = 'Built-in';
      metaRow.appendChild(b);
    }
    info.appendChild(metaRow);

    // Actions
    const actions = document.createElement('div');
    actions.style.cssText = 'display:flex; gap:4px; margin-top:6px; flex-wrap:wrap;';
    const applyBtn = document.createElement('button');
    applyBtn.className = 'btn btn-primary btn-xs';
    applyBtn.textContent = 'Apply';
    applyBtn.addEventListener('click', () => showApplyTemplateDialog(template, false));
    actions.appendChild(applyBtn);
    const editBtn = document.createElement('button');
    editBtn.className = 'btn btn-ghost btn-xs';
    editBtn.textContent = 'Design';
    editBtn.addEventListener('click', () => openTemplateDesigner(template));
    actions.appendChild(editBtn);
    const exportBtn = document.createElement('button');
    exportBtn.className = 'btn btn-ghost btn-xs';
    exportBtn.textContent = 'Export';
    exportBtn.addEventListener('click', () => exportTemplate(template));
    actions.appendChild(exportBtn);
    info.appendChild(actions);

    card.appendChild(info);
    grid.appendChild(card);
  });

  _fillGalleryThumbs(thumbMap);
}

function ensureDesignerShell() {
  const overlay = document.getElementById('tpl-designer-overlay');
  const canvas = document.getElementById('tpl-designer-canvas');
  const toolbar = document.getElementById('tpl-designer-toolbar');
  if (!overlay || !canvas || !toolbar) return;

  if (!document.getElementById('tpl-designer-delete')) {
    const saveBtn = document.getElementById('tpl-designer-save');
    const del = document.createElement('button');
    del.className = 'btn btn-ghost btn-sm text-error';
    del.id = 'tpl-designer-delete';
    del.textContent = 'Delete';
    del.addEventListener('click', deleteEditingTemplate);
    saveBtn?.parentElement?.insertBefore(del, saveBtn);
  }

  if (!document.getElementById('tpl-designer-workspace')) {
    canvas.innerHTML = '';
    canvas.style.cssText = 'flex:1; overflow:hidden; background:#d7dde5; display:grid; grid-template-columns:260px minmax(0,1fr) 300px;';

    const left = document.createElement('aside');
    left.id = 'tpl-zone-panel';
    left.style.cssText = 'overflow:auto; background:var(--base-100,#fff); border-right:1px solid var(--base-300,#d1d5db); padding:0.75rem;';

    const center = document.createElement('main');
    center.id = 'tpl-designer-workspace';
    center.style.cssText = 'position:relative; overflow:auto; padding:1.5rem; display:flex; justify-content:center;';
    const live = document.createElement('div');
    live.id = 'tpl-live-canvas';
    live.style.cssText = 'position:relative;';
    center.appendChild(live);

    const right = document.createElement('aside');
    right.id = 'tpl-match-panel';
    right.style.cssText = 'overflow:auto; background:var(--base-100,#fff); border-left:1px solid var(--base-300,#d1d5db); padding:0.75rem;';

    canvas.appendChild(left);
    canvas.appendChild(center);
    canvas.appendChild(right);

    const guide = document.createElement('div');
    guide.id = 'tpl-snap-guide';
    guide.style.cssText = 'display:none; position:absolute; z-index:50; pointer-events:none; border-left:2px solid #8b3dff; border-top:2px solid #8b3dff;';
    center.appendChild(guide);

    // Zoom controls
    if (!document.getElementById('tpl-zoom-controls')) {
      const zoomBar = document.createElement('div');
      zoomBar.id = 'tpl-zoom-controls';
      zoomBar.style.cssText = 'position:absolute; bottom:12px; right:12px; z-index:20; display:flex; align-items:center; gap:2px; background:var(--base-100,#fff); border:1px solid rgba(14,19,24,0.14); border-radius:8px; padding:3px 5px; box-shadow:0 2px 8px rgba(0,0,0,0.10);';
      let _zoom = 1;
      function applyZoom() {
        const live2 = document.getElementById('tpl-live-canvas');
        if (live2) live2.style.transform = `scale(${_zoom})`;
        if (live2) live2.style.transformOrigin = 'top center';
        zoomLabel.textContent = Math.round(_zoom * 100) + '%';
      }
      const zoomOut = document.createElement('button');
      zoomOut.type = 'button';
      zoomOut.className = 'tpl-toolbar-btn';
      zoomOut.textContent = '−';
      zoomOut.title = 'Zoom out';
      zoomOut.addEventListener('click', () => { _zoom = Math.max(0.25, _zoom - 0.1); applyZoom(); });
      const zoomLabel = document.createElement('span');
      zoomLabel.style.cssText = 'font-size:11px; color:var(--td-muted,#737373); min-width:32px; text-align:center;';
      zoomLabel.textContent = '100%';
      const zoomIn = document.createElement('button');
      zoomIn.type = 'button';
      zoomIn.className = 'tpl-toolbar-btn';
      zoomIn.textContent = '+';
      zoomIn.title = 'Zoom in';
      zoomIn.addEventListener('click', () => { _zoom = Math.min(3, _zoom + 0.1); applyZoom(); });
      const fitBtn = document.createElement('button');
      fitBtn.type = 'button';
      fitBtn.className = 'tpl-toolbar-btn';
      fitBtn.textContent = 'Fit';
      fitBtn.title = 'Fit to window';
      fitBtn.addEventListener('click', () => {
        const ws = document.getElementById('tpl-designer-workspace');
        const live2 = document.getElementById('tpl-live-canvas');
        if (ws && live2) {
          const ratio = (ws.clientWidth - 48) / (live2.scrollWidth || 400);
          _zoom = Math.min(1, ratio);
          applyZoom();
        }
      });
      zoomBar.appendChild(zoomOut);
      zoomBar.appendChild(zoomLabel);
      zoomBar.appendChild(zoomIn);
      zoomBar.appendChild(fitBtn);
      center.appendChild(zoomBar);
    }
  }
  initDesignerCanvasEvents();
}

function openTemplateDesigner(template) {
  ensureDesignerShell();
  loadDesignerFonts();
  const source = cloneTemplate(template);
  _editingTemplate = source;
  if (!_editingTemplate.zones?.length) _editingTemplate.zones = cloneTemplate(getClassicTemplateFallback()).zones;
  _editingSavedSnapshot = templateSnapshot(_editingTemplate);
  _selectedZoneId = sortedZones()[0]?.id || '';
  _selectedElement = null;

  const nameInput = document.getElementById('tpl-designer-name');
  if (nameInput) nameInput.value = _editingTemplate.name || '';

  const overlay = document.getElementById('tpl-designer-overlay');
  if (overlay) overlay.style.display = 'flex';

  renderZoneTree();
  renderMatchEditor();
  renderDesignerToolbar();
  renderDesignerCanvas();
}

function closeTemplateDesigner(force = false) {
  if (!force && designerIsDirty() && !confirm('Discard unsaved template changes?')) return;
  _editingTemplate = null;
  _editingSavedSnapshot = '';
  _selectedZoneId = '';
  _selectedElement = null;
  const overlay = document.getElementById('tpl-designer-overlay');
  if (overlay) overlay.style.display = 'none';
}

function scheduleDesignerCanvasRender() {
  clearTimeout(_designerRenderTimer);
  _designerRenderTimer = setTimeout(renderDesignerCanvas, 300);
}

function renderDesignerCanvas() {
  const live = document.getElementById('tpl-live-canvas');
  if (!live || !_editingTemplate) return;
  const workspace = document.getElementById('tpl-designer-workspace');
  const savedWorkspaceScroll = workspace ? workspace.scrollTop : 0;
  live.innerHTML = '';

  const previousTemplate = cloneTemplate(activeDocTemplate);
  setActiveDocTemplate(_editingTemplate);
  applyDocTemplate();
  _withDesignerSampleData(() => renderPreview());
  previewPane.querySelectorAll('.booklet-page').forEach(page => {
    const clone = page.cloneNode(true);
    clone.querySelectorAll('.preview-page-num, .pg-break-ctrl, .pg-split-ctrl').forEach(el => el.remove());
    clone.classList.add('tpl-canvas-page');
    clone.style.position = 'relative';
    live.appendChild(clone);
  });

  setActiveDocTemplate(previousTemplate);
  applyDocTemplate();
  renderPreview();
  decorateDesignerCanvas();
  if (workspace) requestAnimationFrame(() => { workspace.scrollTop = savedWorkspaceScroll; });
}

function inferCanvasElement(target) {
  const el = target.closest('.cover-church,.cover-title,.cover-date,.ann-item-heading,.ann-body,.ann-qr-wrap,.section-heading,.item-heading,.item-body,.song-copyright,.cal-day-heading,.cal-event-title,.cal-event-time,.cal-event-loc,.serving-week-label,.serving-service-time,.serving-team-name,.serving-role,.serving-row span:not(.serving-role),.sname,.srole,.semail');
  if (!el) return null;
  const text = (el.textContent || '').trim();

  if (el.classList.contains('cover-church')) return { el, binding: 'cover', itemType: '', title: '', elementKey: 'churchName' };
  if (el.classList.contains('cover-title')) return { el, binding: 'cover', itemType: '', title: '', elementKey: 'subtitle' };
  if (el.classList.contains('cover-date')) return { el, binding: 'cover', itemType: '', title: '', elementKey: 'serviceDate' };
  if (el.classList.contains('ann-item-heading')) return { el, binding: 'announcements', itemType: '', title: text, elementKey: 'title' };
  if (el.classList.contains('ann-body')) return { el, binding: 'announcements', itemType: '', title: nearestAnnouncementTitle(el), elementKey: 'body' };
  if (el.classList.contains('ann-qr-wrap')) return { el, binding: 'announcements', itemType: '', title: nearestAnnouncementTitle(el), elementKey: 'url' };
  if (el.classList.contains('section-heading')) return { el, binding: 'pco_items', itemType: 'section', title: text, elementKey: 'heading' };
  if (el.classList.contains('song-copyright')) return { el, binding: 'pco_items', itemType: 'song', title: nearestOowTitle(el), elementKey: 'copyright' };
  if (el.classList.contains('item-heading')) {
    const item = itemByTitle(text);
    const type = item?.type || 'label';
    return { el, binding: 'pco_items', itemType: type, title: text, elementKey: type === 'song' ? 'songTitle' : 'title' };
  }
  if (el.classList.contains('item-body')) {
    const title = nearestOowTitle(el);
    const item = itemByTitle(title);
    const type = item?.type || 'label';
    return { el, binding: 'pco_items', itemType: type, title, elementKey: type === 'song' ? 'stanzaText' : type === 'liturgy' ? 'bodyParagraph' : 'body' };
  }
  if (el.classList.contains('cal-day-heading')) return { el, binding: 'calendar', itemType: '', title: text, elementKey: 'dayHeading' };
  if (el.classList.contains('cal-event-title')) return { el, binding: 'calendar', itemType: '', title: text, elementKey: 'eventTitle' };
  if (el.classList.contains('cal-event-time')) return { el, binding: 'calendar', itemType: '', title: nearestCalendarTitle(el), elementKey: 'eventTime' };
  if (el.classList.contains('cal-event-loc')) return { el, binding: 'calendar', itemType: '', title: nearestCalendarTitle(el), elementKey: 'eventDescription' };
  if (el.classList.contains('serving-week-label')) return { el, binding: 'serving_schedule', itemType: '', title: text, elementKey: 'weekHeading' };
  if (el.classList.contains('serving-service-time')) return { el, binding: 'serving_schedule', itemType: '', title: text, elementKey: 'serviceTime' };
  if (el.classList.contains('serving-team-name')) return { el, binding: 'serving_schedule', itemType: '', title: text, elementKey: 'teamName' };
  if (el.classList.contains('serving-role')) return { el, binding: 'serving_schedule', itemType: '', title: text.replace(/:\s*$/, ''), elementKey: 'positionLabel' };
  if (el.closest('.serving-row')) return { el, binding: 'serving_schedule', itemType: '', title: el.closest('.serving-row')?.querySelector('.serving-role')?.textContent?.replace(/:\s*$/, '') || '', elementKey: 'volunteerName' };
  if (el.classList.contains('sname')) return { el, binding: 'staff', itemType: '', title: text, elementKey: 'staffName' };
  if (el.classList.contains('srole')) return { el, binding: 'staff', itemType: '', title: closestStaffName(el), elementKey: 'staffRole' };
  if (el.classList.contains('semail')) return { el, binding: 'staff', itemType: '', title: closestStaffName(el), elementKey: 'staffEmail' };
  return null;
}

function nearestAnnouncementTitle(el) {
  return el.parentElement?.querySelector('.ann-item-heading')?.textContent?.trim() || '';
}

function nearestOowTitle(el) {
  return el.closest('.order-item')?.querySelector('.item-heading')?.textContent?.trim() || '';
}

function nearestCalendarTitle(el) {
  return el.closest('.cal-event-row')?.querySelector('.cal-event-title')?.textContent?.trim() || '';
}

function closestStaffName(el) {
  return el.closest('tr')?.querySelector('.sname')?.textContent?.trim() || '';
}

function itemByTitle(title) {
  return items.find(item => (item.title || '').trim() === title) || null;
}

function decorateDesignerCanvas() {
  const live = document.getElementById('tpl-live-canvas');
  if (!live) return;

  // Remove stale decorations
  live.querySelectorAll('.tpl-floating-label, .tpl-selection-handle').forEach(el => el.remove());

  live.querySelectorAll('*').forEach(el => {
    const info = inferCanvasElement(el);
    if (!info) return;
    el.classList.add('tpl-selectable-element');
    el.style.cursor = 'pointer';
    el.style.outlineOffset = '2px';

    const isSelected = _selectedElement &&
        info.binding === _selectedElement.binding &&
        info.itemType === _selectedElement.itemType &&
        info.elementKey === _selectedElement.elementKey;

    if (isSelected) {
      el.style.outline = '2px solid #8b3dff';
      el.style.position = el.style.position || 'relative';

      // Corner handles (4 corners)
      [['0%','0%'],['100%','0%'],['0%','100%'],['100%','100%']].forEach(([l, t]) => {
        const h = document.createElement('div');
        h.className = 'tpl-selection-handle';
        h.style.left = `calc(${l} - 4px)`;
        h.style.top = `calc(${t} - 4px)`;
        el.appendChild(h);
      });
    } else {
      el.style.outline = '';
    }

    const fmt = getElementFmtForInfo(info);
    if (fmt?.layout?.position === 'free') {
      el.style.position = 'relative';
      el.style.left = (fmt.layout.x || 0) + 'px';
      el.style.top = (fmt.layout.y || 0) + 'px';
    }
  });
}

function getElementFmtForInfo(info) {
  const zone = bestMatchingZone(_editingTemplate, info.binding, info.itemType, info.title);
  return readZoneElementFmt(zone, info.elementKey);
}

function selectCanvasElement(info) {
  const zone = ensureZoneForSelection(info);
  _selectedZoneId = zone.id;
  _selectedElement = {
    binding: info.binding,
    itemType: info.itemType,
    title: info.title || '',
    elementKey: info.elementKey,
  };
  renderZoneTree();
  renderMatchEditor();
  renderDesignerToolbar();
  decorateDesignerCanvas();
}

function ensureZoneForSelection(info) {
  let zone = bestMatchingZone(_editingTemplate, info.binding, info.itemType, info.title);
  if (zone) return zone;
  zone = {
    id: makeZoneId(info.binding),
    binding: info.binding,
    order: nextZoneOrder(),
    enabled: true,
    match: info.itemType ? { type: info.itemType } : {},
    elements: {},
  };
  _editingTemplate.zones.push(zone);
  return zone;
}

function getSelectedElementFmtForInfo(info) {
  const zone = ensureZoneForSelection(info);
  return getZoneElementFmt(zone, info.elementKey);
}

function nextZoneOrder() {
  return Math.max(0, ...(_editingTemplate?.zones || []).map(z => Number(z.order) || 0)) + 1;
}

function renderZoneTree() {
  const panel = document.getElementById('tpl-zone-panel');
  if (!panel || !_editingTemplate) return;
  const savedScroll = panel.scrollTop;
  panel.innerHTML = '';

  const header = document.createElement('div');
  header.className = 'tpl-panel-title';
  header.textContent = 'Style Rules';
  panel.appendChild(header);

  sortedZones().forEach((zone, idx) => {
    const row = document.createElement('div');
    row.className = 'tpl-zone-row';
    row.draggable = true;
    row.dataset.zoneId = zone.id;
    if (zone.id === _selectedZoneId) row.classList.add('tpl-zone-row--selected');
    row.style.cssText = 'display:grid; grid-template-columns:auto auto 1fr auto auto; gap:0.35rem; align-items:center; padding:0.35rem; border-radius:6px; margin-bottom:0.2rem; border:1px solid transparent;';

    const drag = document.createElement('span');
    drag.textContent = '=';
    drag.style.cursor = 'grab';
    row.appendChild(drag);

    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = zone.enabled !== false;
    cb.addEventListener('change', e => {
      zone.enabled = e.target.checked;
      markDesignerDirty();
    });
    row.appendChild(cb);

    const label = document.createElement('button');
    label.type = 'button';
    label.textContent = zoneLabel(zone);
    label.style.cssText = 'text-align:left; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;';
    label.addEventListener('click', () => {
      _selectedZoneId = zone.id;
      _selectedElement = null;
      renderZoneTree();
      renderMatchEditor();
      renderDesignerToolbar();
    });
    row.appendChild(label);

    const up = document.createElement('button');
    up.type = 'button';
    up.className = 'btn btn-ghost btn-xs';
    up.textContent = 'Up';
    up.disabled = idx === 0;
    up.addEventListener('click', () => moveZone(zone.id, -1));
    row.appendChild(up);

    const down = document.createElement('button');
    down.type = 'button';
    down.className = 'btn btn-ghost btn-xs';
    down.textContent = 'Down';
    down.disabled = idx === sortedZones().length - 1;
    down.addEventListener('click', () => moveZone(zone.id, 1));
    row.appendChild(down);

    row.addEventListener('dragstart', e => e.dataTransfer.setData('text/plain', zone.id));
    row.addEventListener('dragover', e => e.preventDefault());
    row.addEventListener('drop', e => {
      e.preventDefault();
      const draggedId = e.dataTransfer.getData('text/plain');
      reorderZoneBefore(draggedId, zone.id);
    });

    panel.appendChild(row);

    const elements = getZoneElements(zone);
    if (elements.length) {
      const childWrap = document.createElement('div');
      childWrap.style.cssText = 'margin:0 0 0.35rem 1.35rem; display:grid; gap:0.15rem;';
      elements.forEach(elDesc => {
        const child = document.createElement('button');
        child.type = 'button';
        child.textContent = elDesc.label;
        const elSelected = _selectedZoneId === zone.id && _selectedElement?.elementKey === elDesc.key;
        child.style.cssText = `font-size:0.75rem; text-align:left; padding:0.18rem 0.35rem; border-radius:4px; background:${elSelected ? 'rgba(139,61,255,0.12)' : 'transparent'}; color:${elSelected ? '#8b3dff' : 'inherit'}; font-weight:${elSelected ? '600' : 'normal'};`;
        child.addEventListener('click', () => {
          _selectedZoneId = zone.id;
          _selectedElement = { binding: zone.binding, itemType: zone.match?.type || '', title: zone.match?.title || zone.match?.titleContains || '', elementKey: elDesc.key };
          renderZoneTree();
          renderMatchEditor();
          renderDesignerToolbar();
          decorateDesignerCanvas();
        });
        childWrap.appendChild(child);
      });
      if (zone.binding === 'pco_items' && zone.match?.type) {
        const addSpecific = document.createElement('button');
        addSpecific.type = 'button';
        addSpecific.className = 'btn btn-ghost btn-xs';
        addSpecific.textContent = '+ Add title match';
        addSpecific.addEventListener('click', () => addTitleMatchZone(zone));
        childWrap.appendChild(addSpecific);
      }
      panel.appendChild(childWrap);
    }
  });

  const add = document.createElement('button');
  add.className = 'btn btn-primary btn-sm w-full mt-2';
  add.type = 'button';
  add.textContent = '+ Add Style Rule';
  add.addEventListener('click', addZone);
  panel.appendChild(add);
  panel.scrollTop = savedScroll;
}

function moveZone(zoneId, delta) {
  const zones = sortedZones();
  const idx = zones.findIndex(z => z.id === zoneId);
  const targetIdx = idx + delta;
  if (idx < 0 || targetIdx < 0 || targetIdx >= zones.length) return;
  [zones[idx], zones[targetIdx]] = [zones[targetIdx], zones[idx]];
  zones.forEach((z, i) => { z.order = i + 1; });
  markDesignerDirty();
}

function reorderZoneBefore(draggedId, beforeId) {
  if (!draggedId || draggedId === beforeId) return;
  const zones = sortedZones();
  const dragged = zones.find(z => z.id === draggedId);
  if (!dragged) return;
  const without = zones.filter(z => z.id !== draggedId);
  const beforeIdx = without.findIndex(z => z.id === beforeId);
  without.splice(beforeIdx < 0 ? without.length : beforeIdx, 0, dragged);
  without.forEach((z, i) => { z.order = i + 1; });
  markDesignerDirty();
}

async function addZone() {
  const result = await tdShowModal({
    title: 'Add Style Rule',
    confirmText: 'Add',
    fields: [{
      label: 'Bulletin section',
      type: 'select',
      name: 'binding',
      value: 'pco_items',
      options: TEMPLATE_BINDINGS.map(b => ({ value: b, label: bindingLabel(b) })),
    }],
  });
  if (!result) return;
  const { binding } = result;
  if (!TEMPLATE_BINDINGS.includes(binding)) return;
  const zone = {
    id: makeZoneId(binding),
    binding,
    order: nextZoneOrder(),
    enabled: true,
    match: binding === 'pco_items' ? { type: 'label' } : {},
    elements: {},
  };
  _editingTemplate.zones.push(zone);
  _selectedZoneId = zone.id;
  _selectedElement = null;
  markDesignerDirty();
}

async function addTitleMatchZone(parentZone) {
  const result = await tdShowModal({
    title: 'Add Title Match Rule',
    confirmText: 'Add',
    fields: [
      { label: 'Item title to match', type: 'text', name: 'title', placeholder: "e.g. Lord's Prayer" },
      { label: 'Match mode', type: 'select', name: 'mode', value: 'exact', options: [
        { value: 'exact', label: 'Exact match' },
        { value: 'contains', label: 'Contains' },
      ]},
    ],
  });
  if (!result || !result.title.trim()) return;
  const child = {
    id: makeZoneId(parentZone.binding),
    binding: parentZone.binding,
    order: (Number(parentZone.order) || nextZoneOrder()) + 0.1,
    enabled: true,
    match: { type: parentZone.match?.type || 'label' },
    elements: {},
  };
  if (result.mode === 'contains') child.match.titleContains = result.title.trim();
  else child.match.title = result.title.trim();
  _editingTemplate.zones.push(child);
  sortedZones().forEach((z, i) => { z.order = i + 1; });
  _selectedZoneId = child.id;
  _selectedElement = null;
  markDesignerDirty();
}

function renderMatchEditor() {
  const panel = document.getElementById('tpl-match-panel');
  if (!panel || !_editingTemplate) return;
  const savedScroll = panel.scrollTop;
  const zone = getSelectedZone();
  panel.innerHTML = '';

  const title = document.createElement('div');
  title.className = 'tpl-panel-title';
  title.textContent = 'Rule Settings';
  panel.appendChild(title);

  if (!zone) return;

  const bindingSel = makeSelect(TEMPLATE_BINDINGS, zone.binding);
  addField(panel, 'Section', bindingSel);
  bindingSel.addEventListener('change', () => {
    zone.binding = bindingSel.value;
    zone.match = zone.binding === 'pco_items' ? { type: 'label' } : {};
    zone.elements = {};
    _selectedElement = null;
    markDesignerDirty();
  });

  if (zone.binding === 'pco_items') {
    const typeSel = makeSelect(['all'].concat(PCO_TYPES), zone.match?.type || 'all');
    addField(panel, 'Item type', typeSel);
    typeSel.addEventListener('change', () => {
      zone.match = zone.match || {};
      if (typeSel.value === 'all') delete zone.match.type;
      else zone.match.type = typeSel.value;
      markDesignerDirty();
    });
  }

  const matchMode = zone.match?.title ? 'exact' : zone.match?.titleContains ? 'contains' : 'none';
  const modeSel = makeSelect(['none', 'exact', 'contains'], matchMode);
  addField(panel, 'Title filter', modeSel);

  const titleInput = document.createElement('input');
  titleInput.className = 'input input-bordered input-sm w-full';
  titleInput.value = zone.match?.title || zone.match?.titleContains || '';
  titleInput.placeholder = 'Item title';
  addField(panel, 'Match text', titleInput);

  function syncTitleMatch() {
    zone.match = zone.match || {};
    delete zone.match.title;
    delete zone.match.titleContains;
    if (modeSel.value === 'exact' && titleInput.value.trim()) zone.match.title = titleInput.value.trim();
    if (modeSel.value === 'contains' && titleInput.value.trim()) zone.match.titleContains = titleInput.value.trim();
    renderZoneTree();
    renderDesignerToolbar();
    badge.textContent = zoneSpecificityText(zone);
    scheduleDesignerCanvasRender();
  }
  modeSel.addEventListener('change', syncTitleMatch);
  titleInput.addEventListener('input', syncTitleMatch);

  const badge = document.createElement('div');
  badge.className = 'text-xs text-base-content/70 bg-base-200 rounded p-2 my-3';
  badge.textContent = zoneSpecificityText(zone);
  panel.appendChild(badge);

  const addSpecific = document.createElement('button');
  addSpecific.type = 'button';
  addSpecific.className = 'btn btn-ghost btn-sm w-full';
  addSpecific.textContent = '+ Add specific item rule';
  addSpecific.disabled = !(zone.binding === 'pco_items' && zone.match?.type);
  addSpecific.addEventListener('click', () => addTitleMatchZone(zone));
  panel.appendChild(addSpecific);

  const del = document.createElement('button');
  del.type = 'button';
  del.className = 'btn btn-ghost btn-sm text-error w-full mt-2';
  del.textContent = 'Delete Rule';
  del.addEventListener('click', () => deleteZone(zone.id));
  panel.appendChild(del);
  panel.scrollTop = savedScroll;
}

function addField(parent, labelText, control) {
  const label = document.createElement('label');
  label.className = 'text-xs font-medium block mt-2 mb-1';
  label.textContent = labelText;
  parent.appendChild(label);
  parent.appendChild(control);
}

function makeSelect(values, current) {
  const sel = document.createElement('select');
  sel.className = 'select select-bordered select-sm w-full';
  values.forEach(v => {
    const value = typeof v === 'object' ? v.value : v;
    const opt = document.createElement('option');
    opt.value = value;
    opt.textContent = typeof v === 'object' ? v.label : v;
    sel.appendChild(opt);
  });
  sel.value = current;
  return sel;
}

function deleteZone(zoneId) {
  if (!confirm('Delete this zone?')) return;
  _editingTemplate.zones = (_editingTemplate.zones || []).filter(z => z.id !== zoneId);
  _selectedZoneId = sortedZones()[0]?.id || '';
  _selectedElement = null;
  markDesignerDirty();
}

function renderDesignerToolbar() {
  const toolbar = document.getElementById('tpl-designer-toolbar');
  if (!toolbar || !_editingTemplate) return;
  toolbar.innerHTML = '';

  if (!_selectedElement) {
    // Page cluster
    const pageSelect = makeToolbarSelect(Object.keys(PAGE_SIZE_PRESETS), _editingTemplate.pageSize || '5.5x8.5');
    pageSelect.addEventListener('change', () => {
      _editingTemplate.pageSize = pageSelect.value;
      markDesignerDirty();
    });
    toolbar.appendChild(toolbarCluster('Page', [pageSelect]));

    toolbar.appendChild(toolbarSep());

    // Font cluster
    const fontPicker = makeFontSelect(designerFontOptions(), _editingTemplate.cssVars?.fontFamily || 'system-ui', val => {
      _editingTemplate.cssVars = _editingTemplate.cssVars || {};
      _editingTemplate.cssVars.fontFamily = val;
      markDesignerDirty();
    });
    toolbar.appendChild(toolbarCluster('Font', [fontPicker]));

    toolbar.appendChild(toolbarSep());

    // Colors cluster
    const swatches = [
      ['Primary', 'primary', '#111827'],
      ['Muted',   'muted',   '#6b7280'],
      ['Accent',  'accent',  '#172429'],
      ['Border',  'border',  '#e5e7eb'],
    ].map(([label, key, fallback]) => colorSwatchBtn(label, _editingTemplate.cssVars?.[key] || fallback, val => {
      _editingTemplate.cssVars = _editingTemplate.cssVars || {};
      _editingTemplate.cssVars[key] = val;
      markDesignerDirty();
    }));
    toolbar.appendChild(toolbarCluster('Colors', swatches));
    return;
  }

  const zone = getZoneById(_selectedZoneId);
  const fmt = getZoneElementFmt(zone, _selectedElement.elementKey);

  // Breadcrumb
  const crumb = document.createElement('span');
  crumb.style.cssText = 'font-size:12px;color:var(--td-muted,#737373);white-space:nowrap;padding:0 4px;';
  crumb.textContent = `${zoneLabel(zone)} / ${_selectedElement.elementKey.replace(/([A-Z])/g, ' $1').toLowerCase()}`;
  toolbar.appendChild(crumb);

  toolbar.appendChild(toolbarSep());

  // Font cluster
  const fontPicker = makeFontSelect([{ value: '', label: '(default)' }].concat(designerFontOptions()), fmt.fontFamily || '', val => updateSelectedFmt('fontFamily', val));
  const sizePicker = makeSizePicker(fmt.size || '', val => updateSelectedFmt('size', val));
  toolbar.appendChild(toolbarCluster('Font', [fontPicker, sizePicker]));

  toolbar.appendChild(toolbarSep());

  // Text cluster: B / I / U + align L/C/R
  const boldBtn  = toolbarIconBtn('B',  !!fmt.bold,      () => updateSelectedFmt('bold',      !fmt.bold),      'bold');
  const italBtn  = toolbarIconBtn('I',  !!fmt.italic,    () => updateSelectedFmt('italic',    !fmt.italic),    'italic');
  const undlBtn  = toolbarIconBtn('U',  !!fmt.underline, () => updateSelectedFmt('underline', !fmt.underline), 'underline');
  const alignL   = toolbarIconBtn('⬤L', fmt.align==='left',   () => updateSelectedFmt('align', fmt.align==='left'   ? '' : 'left'));
  const alignC   = toolbarIconBtn('⬤C', fmt.align==='center', () => updateSelectedFmt('align', fmt.align==='center' ? '' : 'center'));
  const alignR   = toolbarIconBtn('⬤R', fmt.align==='right',  () => updateSelectedFmt('align', fmt.align==='right'  ? '' : 'right'));
  // Use SVG-free unicode that's readable
  alignL.textContent = '←'; alignL.title = 'Align left';
  alignC.textContent = '↔'; alignC.title = 'Align center';
  alignR.textContent = '→'; alignR.title = 'Align right';
  toolbar.appendChild(toolbarCluster('Text', [boldBtn, italBtn, undlBtn, alignL, alignC, alignR]));

  toolbar.appendChild(toolbarSep());

  // Color cluster
  const colorSwatch = colorSwatchBtn('Color', fmt.color || '#172429', val => updateSelectedFmt('color', val));
  toolbar.appendChild(toolbarCluster('Color', [colorSwatch]));

  // Layout cluster
  const layoutSelect = makeToolbarSelect(['', 'left', 'center', 'right', 'space-between'], fmt.layout?.align || '');
  layoutSelect.addEventListener('change', () => updateSelectedLayout({ align: layoutSelect.value }));
  toolbar.appendChild(toolbarCluster('Layout', [layoutSelect]));

  toolbar.appendChild(toolbarSep());

  // Reset button
  const reset = document.createElement('button');
  reset.type = 'button';
  reset.className = 'tpl-toolbar-btn';
  reset.textContent = 'Reset';
  reset.style.color = 'var(--td-muted,#737373)';
  reset.addEventListener('click', resetSelectedFmt);
  toolbar.appendChild(reset);
}

function toolbarCluster(label, children) {
  const wrap = document.createElement('div');
  wrap.className = 'tpl-toolbar-cluster';
  const lbl = document.createElement('span');
  lbl.className = 'tpl-toolbar-cluster-label';
  lbl.textContent = label;
  wrap.appendChild(lbl);
  children.forEach(c => wrap.appendChild(c));
  return wrap;
}

function toolbarSep() {
  const sep = document.createElement('div');
  sep.className = 'tpl-toolbar-sep';
  return sep;
}

function makeToolbarSelect(options, value) {
  const sel = document.createElement('select');
  sel.className = 'tpl-toolbar-select';
  options.forEach(opt => {
    const o = document.createElement('option');
    o.value = opt;
    o.textContent = opt || '(default)';
    if (opt === value) o.selected = true;
    sel.appendChild(o);
  });
  return sel;
}

function makeSizePicker(value, onChange) {
  const MIN_PT = 5;
  const MAX_PT = 72;
  const DEFAULT_PT = 10;

  const wrap = document.createElement('div');
  wrap.style.cssText = 'display:flex;align-items:center;gap:1px;';

  const dec = document.createElement('button');
  dec.type = 'button';
  dec.className = 'tpl-toolbar-btn';
  dec.textContent = '−';
  dec.style.cssText = 'width:22px;height:28px;padding:0;font-size:15px;flex-shrink:0;';

  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'tpl-toolbar-select';
  input.style.cssText = 'width:46px;text-align:center;padding:0 2px;font-family:inherit;';
  input.value = value ? value : '—';

  const inc = document.createElement('button');
  inc.type = 'button';
  inc.className = 'tpl-toolbar-btn';
  inc.textContent = '+';
  inc.style.cssText = 'width:22px;height:28px;padding:0;font-size:15px;flex-shrink:0;';

  function setPt(pt) {
    if (pt === null) { input.value = '—'; onChange(''); return; }
    pt = Math.max(MIN_PT, Math.min(MAX_PT, Math.round(pt)));
    input.value = pt + 'pt';
    onChange(pt + 'pt');
  }

  function currentPt() {
    const m = input.value.match(/(\d+(\.\d+)?)/);
    return m ? parseFloat(m[1]) : null;
  }

  dec.addEventListener('click', () => {
    const cur = currentPt();
    setPt(cur !== null ? cur - 1 : DEFAULT_PT);
  });

  inc.addEventListener('click', () => {
    const cur = currentPt();
    setPt(cur !== null ? cur + 1 : DEFAULT_PT);
  });

  input.addEventListener('keydown', e => {
    if (e.key === 'ArrowUp')   { e.preventDefault(); inc.click(); }
    if (e.key === 'ArrowDown') { e.preventDefault(); dec.click(); }
    if (e.key === 'Enter')     { input.blur(); }
  });

  input.addEventListener('blur', () => {
    const raw = input.value.trim();
    if (!raw || raw === '—') { setPt(null); return; }
    const pt = parseFloat(raw);
    if (!isNaN(pt)) setPt(pt);
    else input.value = currentPt() !== null ? currentPt() + 'pt' : '—';
  });

  wrap.appendChild(dec);
  wrap.appendChild(input);
  wrap.appendChild(inc);
  return wrap;
}

function _closeFontPickers() {
  document.querySelectorAll('.tpl-font-picker-panel').forEach(p => { p.style.display = 'none'; });
}

function makeFontSelect(options, value, onChange) {
  const normalized = options.map(o => typeof o === 'string' ? { value: o, label: o } : o);
  const current = normalized.find(o => o.value === value);
  const displayLabel = current?.label || value || '(default)';

  const wrap = document.createElement('div');
  wrap.className = 'tpl-font-picker';

  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'tpl-toolbar-select tpl-font-picker-btn';
  btn.style.fontFamily = value ? `"${value}",sans-serif` : 'inherit';
  btn.style.minWidth = '130px';
  btn.style.textAlign = 'left';
  btn.style.cursor = 'pointer';
  btn.textContent = displayLabel;
  wrap.appendChild(btn);

  const panel = document.createElement('div');
  panel.className = 'tpl-font-picker-panel';
  panel.style.cssText = 'display:none;position:absolute;z-index:950;background:#fff;border:1px solid #e5e7eb;border-radius:6px;box-shadow:0 4px 16px rgba(0,0,0,0.14);max-height:240px;overflow-y:auto;min-width:180px;padding:4px 0;';
  wrap.appendChild(panel);

  normalized.forEach(opt => {
    const item = document.createElement('div');
    item.className = 'tpl-font-picker-item' + (opt.value === value ? ' active' : '');
    item.style.cssText = `padding:6px 14px;cursor:pointer;font-size:13px;white-space:nowrap;font-family:${opt.value ? `"${opt.value}",sans-serif` : 'inherit'};`;
    item.textContent = opt.label || opt.value || '(default)';
    item.addEventListener('mouseenter', () => { item.style.background = '#f3f4f6'; });
    item.addEventListener('mouseleave', () => { item.style.background = opt.value === value ? '#eef2ff' : ''; });
    if (opt.value === value) item.style.background = '#eef2ff';
    item.addEventListener('mousedown', e => {
      e.preventDefault();
      btn.textContent = item.textContent;
      btn.style.fontFamily = opt.value ? `"${opt.value}",sans-serif` : 'inherit';
      panel.style.display = 'none';
      onChange(opt.value);
    });
    panel.appendChild(item);
  });

  btn.addEventListener('click', e => {
    e.stopPropagation();
    const open = panel.style.display !== 'none';
    _closeFontPickers();
    if (!open) {
      panel.style.display = 'block';
      const rect = wrap.getBoundingClientRect();
      const spaceBelow = window.innerHeight - rect.bottom;
      if (spaceBelow < 250 && rect.top > 250) {
        panel.style.top = 'auto';
        panel.style.bottom = '100%';
      } else {
        panel.style.top = '100%';
        panel.style.bottom = 'auto';
      }
    }
  });

  return wrap;
}

function toolbarIconBtn(text, active, onClick, style) {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'tpl-toolbar-btn' + (active ? ' active' : '');
  btn.textContent = text;
  if (style === 'bold')      btn.style.fontWeight = '700';
  if (style === 'italic')    btn.style.fontStyle  = 'italic';
  if (style === 'underline') btn.style.textDecoration = 'underline';
  btn.addEventListener('click', onClick);
  return btn;
}

function colorSwatchBtn(label, value, onChange) {
  const wrap = document.createElement('label');
  wrap.className = 'tpl-color-swatch-wrap';
  wrap.title = label;
  const preview = document.createElement('div');
  preview.className = 'tpl-color-swatch-preview';
  preview.style.background = value;
  const name = document.createElement('span');
  name.className = 'tpl-color-swatch-name';
  name.textContent = label;
  const input = document.createElement('input');
  input.type = 'color';
  input.value = value;
  input.addEventListener('input', () => {
    preview.style.background = input.value;
    onChange(input.value);
  });
  wrap.appendChild(preview);
  wrap.appendChild(name);
  wrap.appendChild(input);
  return wrap;
}

// Legacy helpers kept for any remaining callers
function toolbarGroup(label, control) {
  const wrap = document.createElement('label');
  wrap.style.cssText = 'display:flex; align-items:center; gap:0.35rem;';
  const span = document.createElement('span');
  span.className = 'text-xs text-base-content/60';
  span.textContent = label;
  wrap.appendChild(span);
  wrap.appendChild(control);
  return wrap;
}

function toolbarText(text) {
  const span = document.createElement('span');
  span.className = 'text-sm font-medium';
  span.textContent = text;
  return span;
}

function toggleButton(text, active, onClick) {
  return toolbarIconBtn(text, active, onClick);
}

function updateSelectedFmt(key, value) {
  const zone = getZoneById(_selectedZoneId);
  if (!zone || !_selectedElement) return;
  const fmt = getZoneElementFmt(zone, _selectedElement.elementKey);
  if (value === '' || value === undefined) delete fmt[key];
  else fmt[key] = value;
  markDesignerDirty();
}

function updateSelectedLayout(partial) {
  const zone = getZoneById(_selectedZoneId);
  if (!zone || !_selectedElement) return;
  const fmt = getZoneElementFmt(zone, _selectedElement.elementKey);
  fmt.layout = Object.assign({}, fmt.layout || {}, partial);
  markDesignerDirty();
}

function resetSelectedFmt() {
  const zone = getZoneById(_selectedZoneId);
  if (!zone || !_selectedElement || !zone.elements) return;
  delete zone.elements[_selectedElement.elementKey];
  markDesignerDirty();
}

function showApplyTemplateDialog(template, exitAfterChoice) {
  _pendingTemplateApply = cloneTemplate(template);
  _pendingApplyExitAfterChoice = !!exitAfterChoice;
  const msg = document.getElementById('tpl-apply-dialog-msg');
  if (msg) msg.textContent = `Apply "${_pendingTemplateApply.name || 'this template'}" to the current project?`;
  const dialog = document.getElementById('tpl-apply-dialog');
  if (dialog) dialog.style.display = 'flex';
}

function hideApplyTemplateDialog() {
  _pendingTemplateApply = null;
  const dialog = document.getElementById('tpl-apply-dialog');
  if (dialog) dialog.style.display = 'none';
  if (_pendingApplyExitAfterChoice) {
    _pendingApplyExitAfterChoice = false;
    closeTemplateDesigner(true);
  }
}

function applyPendingTemplate() {
  if (!_pendingTemplateApply) return;
  setActiveDocTemplate(_pendingTemplateApply);
  applyDocTemplate();
  schedulePreviewUpdate();
  scheduleProjectPersist();
  apiFetch('/api/settings', 'POST', { docTemplate: activeDocTemplate })
    .catch(err => setStatus('Template save failed: ' + (err.message || err), 'error'));
  setStatus(`Applied "${activeDocTemplate.name || 'Template'}".`, 'success');
  const shouldExit = _pendingApplyExitAfterChoice;
  _pendingApplyExitAfterChoice = false;
  hideApplyTemplateDialog();
  if (shouldExit) closeTemplateDesigner(true);
}

async function saveEditingTemplate(saveAs) {
  if (!_editingTemplate) return;
  const nameInput = document.getElementById('tpl-designer-name');
  const nextTemplate = cloneTemplate(_editingTemplate);
  nextTemplate.name = (nameInput?.value || '').trim() || 'Untitled Template';

  if (saveAs) {
    const result = await tdShowModal({
      title: 'Save Template As',
      confirmText: 'Save',
      fields: [{ label: 'Template name', type: 'text', name: 'name', value: `Copy of ${nextTemplate.name}` }],
    });
    if (!result) return;
    nextTemplate.name = result.name.trim() || nextTemplate.name;
    nextTemplate.id = makeTemplateId();
    nextTemplate.builtIn = false;
  }

  if (nextTemplate.builtIn) {
    nextTemplate.id = makeTemplateId();
    nextTemplate.name = `Copy of ${nextTemplate.name || 'Template'}`;
    nextTemplate.builtIn = false;
  }

  try {
    await apiFetch('/api/templates', 'POST', nextTemplate);
    const existingIdx = templates.findIndex(t => t.id === nextTemplate.id);
    if (existingIdx >= 0) templates[existingIdx] = nextTemplate;
    else templates.push(nextTemplate);
    _editingTemplate = nextTemplate;
    _editingSavedSnapshot = templateSnapshot(_editingTemplate);
    setStatus(`Saved "${nextTemplate.name}".`, 'success');
    renderTemplateGallery();
    showApplyTemplateDialog(nextTemplate, true);
  } catch (err) {
    setStatus('Template save failed: ' + (err.message || err), 'error');
  }
}

async function startNewTemplate() {
  const list = getTemplateList();
  const result = await tdShowModal({
    title: 'New Template',
    confirmText: 'Create',
    fields: [{
      label: 'Start from a base template',
      type: 'template-list',
      name: 'idx',
      value: 0,
      options: list.map(t => ({ value: t.id, label: t.name || t.id })),
    }],
  });
  if (result === null) return;
  const idx = Math.max(0, Math.min(list.length - 1, result.idx));
  const base = cloneTemplate(list[idx]);
  base.id = makeTemplateId();
  base.name = `Copy of ${base.name || 'Template'}`;
  base.builtIn = false;
  openTemplateDesigner(base);
  _editingSavedSnapshot = '';
}

async function deleteEditingTemplate() {
  if (!_editingTemplate) return;
  if (_editingTemplate.builtIn) {
    setStatus('Built-in templates cannot be deleted.', 'error');
    return;
  }
  if (!confirm(`Delete "${_editingTemplate.name || 'this template'}"? This cannot be undone.`)) return;
  try {
    await apiFetch(`/api/templates/${encodeURIComponent(_editingTemplate.id)}`, 'DELETE');
    setTemplates(templates.filter(t => t.id !== _editingTemplate.id));
    renderTemplateGallery();
    closeTemplateDesigner(true);
    setStatus('Template deleted.', 'success');
  } catch (err) {
    setStatus('Template delete failed: ' + (err.message || err), 'error');
  }
}

function initDesignerCanvasEvents() {
  const workspace = document.getElementById('tpl-designer-workspace');
  if (!workspace || workspace.dataset.tplEvents === '1') return;
  workspace.dataset.tplEvents = '1';

  workspace.addEventListener('click', e => {
    const info = inferCanvasElement(e.target);
    if (!info) {
      _selectedElement = null;
      renderDesignerToolbar();
      decorateDesignerCanvas();
      return;
    }
    e.preventDefault();
    selectCanvasElement(info);
  });

  workspace.addEventListener('pointerdown', e => {
    const info = inferCanvasElement(e.target);
    if (!info) return;
    selectCanvasElement(info);
    const page = info.el.closest('.booklet-page');
    const pageRect = page?.getBoundingClientRect();
    const elRect = info.el.getBoundingClientRect();
    const startLeft = parseFloat(info.el.style.left || '0') || 0;
    const startTop = parseFloat(info.el.style.top || '0') || 0;
    _designerDrag = {
      info,
      startX: e.clientX,
      startY: e.clientY,
      startLeft,
      startTop,
      width: elRect.width,
      height: elRect.height,
      originPageLeft: pageRect ? elRect.left - pageRect.left - startLeft : 0,
      originPageTop: pageRect ? elRect.top - pageRect.top - startTop : 0,
    };
    info.el.setPointerCapture?.(e.pointerId);
  });

  workspace.addEventListener('pointermove', e => {
    if (!_designerDrag) return;
    const dx = e.clientX - _designerDrag.startX;
    const dy = e.clientY - _designerDrag.startY;
    const snapped = snapDrag(_designerDrag.startLeft + dx, _designerDrag.startTop + dy, _designerDrag.info.el);
    _designerDrag.info.el.style.position = 'relative';
    _designerDrag.info.el.style.left = snapped.x + 'px';
    _designerDrag.info.el.style.top = snapped.y + 'px';
  });

  workspace.addEventListener('pointerup', () => finishDesignerDrag());
  workspace.addEventListener('pointercancel', () => finishDesignerDrag());
}

function snapDrag(x, y, el) {
  const threshold = 8;
  const page = el.closest('.booklet-page');
  const guide = document.getElementById('tpl-snap-guide');
  let snappedX = x;
  let snappedY = y;
  let showGuide = false;
  if (page) {
    const pageRect = page.getBoundingClientRect();
    const drag = _designerDrag || {};
    const originLeft = drag.originPageLeft || 0;
    const originTop = drag.originPageTop || 0;
    const width = drag.width || el.getBoundingClientRect().width;
    const height = drag.height || el.getBoundingClientRect().height;
    const target = {
      left: originLeft + x,
      right: originLeft + x + width,
      top: originTop + y,
      bottom: originTop + y + height,
      midX: originLeft + x + width / 2,
      midY: originTop + y + height / 2,
    };

    const candidates = [
      { axis: 'x', value: -originLeft, delta: Math.abs(target.left) },
      { axis: 'x', value: pageRect.width - originLeft - width, delta: Math.abs(target.right - pageRect.width) },
      { axis: 'x', value: pageRect.width / 2 - originLeft - width / 2, delta: Math.abs(target.midX - pageRect.width / 2) },
      { axis: 'y', value: -originTop, delta: Math.abs(target.top) },
      { axis: 'y', value: pageRect.height - originTop - height, delta: Math.abs(target.bottom - pageRect.height) },
      { axis: 'y', value: pageRect.height / 2 - originTop - height / 2, delta: Math.abs(target.midY - pageRect.height / 2) },
    ];

    page.querySelectorAll('.tpl-selectable-element').forEach(other => {
      if (other === el) return;
      const rect = other.getBoundingClientRect();
      const otherBox = {
        left: rect.left - pageRect.left,
        right: rect.right - pageRect.left,
        top: rect.top - pageRect.top,
        bottom: rect.bottom - pageRect.top,
        midX: rect.left - pageRect.left + rect.width / 2,
        midY: rect.top - pageRect.top + rect.height / 2,
      };
      candidates.push(
        { axis: 'x', value: otherBox.left - originLeft, delta: Math.abs(target.left - otherBox.left) },
        { axis: 'x', value: otherBox.right - originLeft - width, delta: Math.abs(target.right - otherBox.right) },
        { axis: 'x', value: otherBox.midX - originLeft - width / 2, delta: Math.abs(target.midX - otherBox.midX) },
        { axis: 'y', value: otherBox.top - originTop, delta: Math.abs(target.top - otherBox.top) },
        { axis: 'y', value: otherBox.bottom - originTop - height, delta: Math.abs(target.bottom - otherBox.bottom) },
        { axis: 'y', value: otherBox.midY - originTop - height / 2, delta: Math.abs(target.midY - otherBox.midY) },
      );
    });

    const bestX = candidates.filter(c => c.axis === 'x' && c.delta < threshold).sort((a, b) => a.delta - b.delta)[0];
    const bestY = candidates.filter(c => c.axis === 'y' && c.delta < threshold).sort((a, b) => a.delta - b.delta)[0];
    if (bestX) { snappedX = bestX.value; showGuide = true; }
    if (bestY) { snappedY = bestY.value; showGuide = true; }
    if (guide && showGuide) {
      const parentRect = guide.parentElement.getBoundingClientRect();
      guide.style.left = (pageRect.left - parentRect.left + originLeft + snappedX) + 'px';
      guide.style.top = (pageRect.top - parentRect.top + originTop + snappedY) + 'px';
      guide.style.width = bestY ? pageRect.width + 'px' : '0';
      guide.style.height = bestX ? pageRect.height + 'px' : '0';
      guide.style.borderLeftWidth = bestX ? '2px' : '0';
      guide.style.borderTopWidth = bestY ? '2px' : '0';
    }
  }
  if (guide) guide.style.display = showGuide ? 'block' : 'none';
  return { x: Math.round(snappedX), y: Math.round(snappedY) };
}

function finishDesignerDrag() {
  if (!_designerDrag) return;
  const left = parseFloat(_designerDrag.info.el.style.left || '0') || 0;
  const top = parseFloat(_designerDrag.info.el.style.top || '0') || 0;
  const zone = getZoneById(_selectedZoneId);
  if (zone && _selectedElement) {
    const fmt = getZoneElementFmt(zone, _selectedElement.elementKey);
    const inlineLayout = deriveInlineLayoutForDrop(_designerDrag.info.el, _selectedElement);
    fmt.layout = inlineLayout || Object.assign({}, fmt.layout || {}, { position: 'free', x: left, y: top });
  }
  const guide = document.getElementById('tpl-snap-guide');
  if (guide) guide.style.display = 'none';
  _designerDrag = null;
  markDesignerDirty();
}

function deriveInlineLayoutForDrop(el, selected) {
  if (!el || !selected || selected.binding !== 'pco_items') return null;
  const item = el.closest('.order-item');
  if (!item) return null;
  const candidates = Array.from(item.querySelectorAll('.tpl-selectable-element')).filter(candidate => {
    if (candidate === el) return false;
    const info = inferCanvasElement(candidate);
    if (!info || info.binding !== selected.binding) return false;
    if (info.itemType !== selected.itemType || info.title !== selected.title) return false;
    return info.elementKey === 'songTitle' || info.elementKey === 'title';
  });
  const target = candidates[0];
  if (!target || typeof deriveInlineDropLayoutCore !== 'function') return null;
  const dragRect = el.getBoundingClientRect();
  const targetRect = target.getBoundingClientRect();
  return deriveInlineDropLayoutCore({
    left: dragRect.left,
    right: dragRect.right,
    top: dragRect.top,
    bottom: dragRect.bottom,
  }, {
    left: targetRect.left,
    right: targetRect.right,
    top: targetRect.top,
    bottom: targetRect.bottom,
  });
}

function initTemplateControls() {
  if (_templatesInitialized) return;
  _templatesInitialized = true;

  document.getElementById('tpl-new-btn')?.addEventListener('click', startNewTemplate);
  document.getElementById('tpl-designer-back')?.addEventListener('click', () => closeTemplateDesigner(false));
  document.getElementById('tpl-designer-export')?.addEventListener('click', () => exportTemplate(_editingTemplate));
  document.getElementById('tpl-designer-save')?.addEventListener('click', () => saveEditingTemplate(false));
  document.getElementById('tpl-designer-save-as')?.addEventListener('click', () => saveEditingTemplate(true));
  document.getElementById('tpl-apply-cancel')?.addEventListener('click', hideApplyTemplateDialog);
  document.getElementById('tpl-apply-confirm')?.addEventListener('click', applyPendingTemplate);
  document.getElementById('tpl-import-btn')?.addEventListener('click', () => {
    document.getElementById('tpl-import-input')?.click();
  });
  document.getElementById('tpl-import-input')?.addEventListener('change', e => {
    importTemplateFile(e.target.files?.[0]);
  });
  document.getElementById('tpl-fonts-btn')?.addEventListener('click', showFontsModal);
  document.getElementById('tpl-font-upload-input')?.addEventListener('change', e => {
    uploadFontFile(e.target.files?.[0]).then(() => showFontsModal()).finally(() => { e.target.value = ''; });
  });
  document.getElementById('tpl-designer-name')?.addEventListener('input', e => {
    if (!_editingTemplate) return;
    _editingTemplate.name = e.target.value;
    markDesignerDirty();
  });
  document.addEventListener('click', _closeFontPickers);
  loadDesignerFonts();
  initDesignerCanvasEvents();
}
