const express = require("express");
const usersRouter = require("./routes/users");

const app = express();
app.use(express.json());
app.use("/users", usersRouter);

app.get("/health", (req, res) => res.json({ ok: true }));

const port = process.env.PORT || 3000;
app.listen(port, () => console.log(`listening on ${port}`));