import moment from "moment";
export const shortDate = (d) => moment(d).format("DD/MM/YYYY");
export const fromNow = (d) => moment(d).fromNow();
