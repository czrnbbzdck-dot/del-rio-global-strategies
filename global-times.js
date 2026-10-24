const clocks = [...document.querySelectorAll(".global-clock")];

const formatters = clocks.map((clock) => {
  const timeZone = clock.dataset.timeZone;
  return {
    time: new Intl.DateTimeFormat("en-US", {
      timeZone,
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    }),
    date: new Intl.DateTimeFormat("en-US", {
      timeZone,
      month: "long",
      day: "numeric",
      year: "numeric",
    }),
    timeElement: clock.querySelector(".global-clock-time"),
    dateElement: clock.querySelector(".global-clock-date"),
  };
});

const updateClocks = () => {
  const now = new Date();
  const instant = now.toISOString();

  for (const formatter of formatters) {
    formatter.timeElement.dateTime = instant;
    formatter.timeElement.textContent = formatter.time.format(now);
    formatter.dateElement.dateTime = instant;
    formatter.dateElement.textContent = formatter.date.format(now);
  }
};

updateClocks();
window.setInterval(updateClocks, 60_000);
