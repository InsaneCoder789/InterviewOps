// These dates are an interactive design example, not live booking data.
const days = [
  {label:'Saturday, 12 December', name:'System design', start:'10:00', end:'11:00', offset:1},
  {label:'Sunday, 13 December'},
  {label:'Friday, 18 December', name:'Behavioural interview', start:'14:00', end:'15:00', offset:5}
];
let selected = 0;
const label = document.querySelector('#selected-day');
const grid = document.querySelector('#timeline-grid');
const previous = document.querySelector('#previous-day');
const next = document.querySelector('#next-day');
function renderDay() {
  const day = days[selected];
  label.textContent = day.label;
  grid.replaceChildren();
  if (day.name) {
    const event = document.createElement('div');
    event.className = 'timeline-event';
    event.style.setProperty('--start', day.offset);
    event.style.setProperty('--duration', 1);
    const name = document.createElement('span'); name.textContent = day.name;
    const time = document.createElement('small'); time.textContent = `${day.start}–${day.end}`;
    event.append(name, time); grid.append(event);
  } else {
    const empty = document.createElement('span'); empty.className = 'timeline-empty';
    empty.textContent = 'No illustrative sessions on this day.'; grid.append(empty);
  }
  previous.disabled = selected === 0;
  next.disabled = selected === days.length - 1;
}
previous.addEventListener('click', () => { if (selected > 0) { selected--; renderDay(); } });
next.addEventListener('click', () => { if (selected < days.length - 1) { selected++; renderDay(); } });
renderDay();
