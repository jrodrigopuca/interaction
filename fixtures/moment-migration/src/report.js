import moment from "moment";
export const monthLabel = (d) => moment(d).format("MMMM YYYY");
export const isWeekend = (d) => [0, 6].includes(moment(d).day());
