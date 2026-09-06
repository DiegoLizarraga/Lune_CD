/* Lune CD — inline SVG icon set (Lucide-style, 2px stroke).
   Exposed on window for the kit scripts. */
const I = (paths, props = {}) => (p) =>
  React.createElement('svg', {
    width: 20, height: 20, viewBox: '0 0 24 24', fill: 'none',
    stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round',
    strokeLinejoin: 'round', ...props, ...p,
  }, paths.map((d, i) => React.createElement('path', { key: i, d })));

const IconCloud = I(['M17.5 19a4.5 4.5 0 0 0 0-9h-1.26A8 8 0 1 0 4 15.25']);
const IconCpu = (p) => React.createElement('svg', {
  width:20,height:20,viewBox:'0 0 24 24',fill:'none',stroke:'currentColor',
  strokeWidth:2,strokeLinecap:'round',strokeLinejoin:'round',...p },
  React.createElement('rect',{key:0,x:6,y:6,width:12,height:12,rx:1}),
  React.createElement('path',{key:1,d:'M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2'}));
const IconGear = (p) => React.createElement('svg', {
  width:20,height:20,viewBox:'0 0 24 24',fill:'none',stroke:'currentColor',
  strokeWidth:2,strokeLinecap:'round',strokeLinejoin:'round',...p },
  React.createElement('circle',{key:0,cx:12,cy:12,r:3}),
  React.createElement('path',{key:1,d:'M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z'}));
const IconTrash = I(['M3 6h18','M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6','M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2','M10 11v6','M14 11v6']);
const IconBrain = I(['M12 5a3 3 0 1 0-5.99.14 4 4 0 0 0-1.5 7.06A3.5 3.5 0 0 0 8 18.5 3 3 0 0 0 12 19m0-14a3 3 0 1 1 5.99.14 4 4 0 0 1 1.5 7.06A3.5 3.5 0 0 1 16 18.5 3 3 0 0 1 12 19m0-14v14']);
const IconTool = I(['M14.7 6.3a4 4 0 0 1-5.4 5.4L4 17v3h3l5.3-5.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2-2 2.6-2.6z']);
const IconVolume = I(['M11 5 6 9H2v6h4l5 4z','M19 12a7 7 0 0 0-3-5.7','M15.5 8.5a3.5 3.5 0 0 1 0 5']);
const IconVolumeOff = I(['M11 5 6 9H2v6h4l5 4z','M22 9l-6 6','M16 9l6 6']);
const IconSend = (p) => React.createElement('svg', {
  width:20,height:20,viewBox:'0 0 24 24',fill:'none',stroke:'currentColor',
  strokeWidth:2.4,strokeLinecap:'round',strokeLinejoin:'round',...p },
  React.createElement('path',{key:0,d:'M12 19V5'}),
  React.createElement('path',{key:1,d:'M5 12l7-7 7 7'}));
const IconStop = (p) => React.createElement('svg',{width:18,height:18,viewBox:'0 0 24 24',fill:'currentColor',...p},
  React.createElement('rect',{key:0,x:6,y:6,width:12,height:12,rx:1}));
const IconTelegram = I(['m22 3-9.5 9.5','M22 3 15 21l-4-8-8-4 19-6z']);
const IconMoon = I(['M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z']);
const IconSearch = I(['M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z','m21 21-4.3-4.3']);
const IconBolt = (p) => React.createElement('svg',{width:20,height:20,viewBox:'0 0 24 24',fill:'currentColor',...p},
  React.createElement('path',{key:0,d:'M13 2 4.5 13.5H11l-1 8.5 8.5-11.5H12z'}));
const IconExternal = I(['M15 3h6v6','M10 14 21 3','M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6']);
const IconClip = I(['m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48']);
const IconMic = I(['M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z','M19 10v2a7 7 0 0 1-14 0v-2','M12 19v3']);
const IconUsers = I(['M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2','M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z','M22 21v-2a4 4 0 0 0-3-3.87','M16 3.13a4 4 0 0 1 0 7.75']);
const IconHistory = I(['M3 12a9 9 0 1 0 3-6.7L3 8','M3 3v5h5','M12 7v5l4 2']);

Object.assign(window, {
  IconCloud, IconCpu, IconGear, IconTrash, IconBrain, IconTool,
  IconVolume, IconVolumeOff, IconSend, IconStop, IconTelegram,
  IconMoon, IconSearch, IconBolt, IconExternal, IconClip, IconMic, IconUsers, IconHistory,
});
