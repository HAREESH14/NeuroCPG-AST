error id: file://<WORKSPACE>/benchmarks/datasets/Main.java
file://<WORKSPACE>/benchmarks/datasets/Main.java
### com.thoughtworks.qdox.parser.ParseException: syntax error @[1,1]

error in qdox parser
file content:
```java
offset: 1
uri: file://<WORKSPACE>/benchmarks/datasets/Main.java
text:
```scala
a@@ckage translated;
// samples/all_features.java — comprehensive test of ALL supported features
public class Main {

    // Multiple functions with different return types
    public static int max(int a, int b) {
        return a > b ? a : b;
    }

    public static float average(int a, int b) {
        return (a + b) / 2.0f;
    }

    public static void printRange(int start, int end) {
        for (int i = start; i < end; i++) {
            System.out.println(i);
        }
    }

    public static boolean isEven(int n) {
        return n % 2 == 0;
    }

    public static void main(String[] args) {
        // === Variables: all types ===
        int x = 42;
        float pi = 3.14f;
        double e = 2.718;
        char ch = 'Z';
        long big = 999999;
        short small = 10;

        // === Arithmetic + compound assignments ===
        x += 8;
        x -= 10;
        x *= 2;
        x /= 4;
        System.out.printf("x = %d%n", x);

        // === Prefix / postfix operators ===
        int a = 5;
        a++;
        ++a;
        a--;
        --a;
        System.out.printf("a = %d%n", a);

        // === if / else if / else (nested) ===
        if (x > 100) {
            System.out.println("big");
        } else if (x > 50) {
            System.out.println("medium");
        } else if (x > 10) {
            System.out.println("small");
        } else {
            System.out.println("tiny");
        }

        // === Classic for loop ===
        int sum = 0;
        for (int i = 1; i <= 10; i++) {
            sum += i;
        }
        System.out.printf("sum = %d%n", sum);

        // === While loop ===
        int count = 0;
        while (count < 5) {
            count++;
        }
        System.out.printf("count = %d%n", count);

        // === Do-while loop ===
        int n = 10;
        do {
            n -= 3;
        } while (n > 0);
        System.out.printf("n = %d%n", n);

        // === Break and continue ===
        for (int i = 0; i < 20; i++) {
            if (i % 2 == 0) continue;
            if (i > 9) break;
            System.out.println(i);
        }

        // === 1D array with new ===
        int[] arr = new int[5];
        for (int i = 0; i < 5; i++) {
            arr[i] = i * i;
        }

        // === 1D array with initializer ===
        int[] fib = {1, 1, 2, 3, 5, 8, 13};

        // === 2D array ===
        int[][] grid = new int[3][4];
        for (int i = 0; i < 3; i++) {
            for (int j = 0; j < 4; j++) {
                grid[i][j] = i * 4 + j;
            }
        }

        // === For-each loop ===
        for (int f : fib) {
            System.out.println(f);
        }

        // === Switch with multiple cases + default ===
        int day = 5;
        switch (day) {
            case 1: System.out.println("Mon"); break;
            case 2: System.out.println("Tue"); break;
            case 3: System.out.println("Wed"); break;
            case 4: System.out.println("Thu"); break;
            case 5: System.out.println("Fri"); break;
            case 6: System.out.println("Sat"); break;
            case 7: System.out.println("Sun"); break;
            default: System.out.println("Invalid"); break;
        }

        // === Function calls ===
        int biggest = max(42, 17);
        System.out.printf("max = %d%n", biggest);
        printRange(0, 3);

        // === Ternary expression ===
        int abs_val = x > 0 ? x : -x;
        System.out.printf("abs = %d%n", abs_val);

        // === println with string concatenation ===
        System.out.println("Result: " + biggest);

        // === printf with format specifiers ===
        System.out.printf("pi = %f, ch = %c%n", pi, ch);
    }
}

```

```



#### Error stacktrace:

```
com.thoughtworks.qdox.parser.impl.Parser.yyerror(Parser.java:2025)
	com.thoughtworks.qdox.parser.impl.Parser.yyparse(Parser.java:2147)
	com.thoughtworks.qdox.parser.impl.Parser.parse(Parser.java:2006)
	com.thoughtworks.qdox.library.SourceLibrary.parse(SourceLibrary.java:232)
	com.thoughtworks.qdox.library.SourceLibrary.parse(SourceLibrary.java:190)
	com.thoughtworks.qdox.library.SourceLibrary.addSource(SourceLibrary.java:94)
	com.thoughtworks.qdox.library.SourceLibrary.addSource(SourceLibrary.java:89)
	com.thoughtworks.qdox.library.SortedClassLibraryBuilder.addSource(SortedClassLibraryBuilder.java:162)
	com.thoughtworks.qdox.JavaProjectBuilder.addSource(JavaProjectBuilder.java:174)
	scala.meta.internal.mtags.JavaMtags.indexRoot(JavaMtags.scala:49)
	scala.meta.internal.metals.SemanticdbDefinition$.foreachWithReturnMtags(SemanticdbDefinition.scala:99)
	scala.meta.internal.metals.Indexer.indexSourceFile(Indexer.scala:560)
	scala.meta.internal.metals.Indexer.$anonfun$reindexWorkspaceSources$3(Indexer.scala:691)
	scala.meta.internal.metals.Indexer.$anonfun$reindexWorkspaceSources$3$adapted(Indexer.scala:688)
	scala.collection.IterableOnceOps.foreach(IterableOnce.scala:630)
	scala.collection.IterableOnceOps.foreach$(IterableOnce.scala:628)
	scala.collection.AbstractIterator.foreach(Iterator.scala:1313)
	scala.meta.internal.metals.Indexer.reindexWorkspaceSources(Indexer.scala:688)
	scala.meta.internal.metals.MetalsLspService.$anonfun$onChange$2(MetalsLspService.scala:940)
	scala.runtime.java8.JFunction0$mcV$sp.apply(JFunction0$mcV$sp.scala:18)
	scala.concurrent.Future$.$anonfun$apply$1(Future.scala:691)
	scala.concurrent.impl.Promise$Transformation.run(Promise.scala:500)
	java.base/java.util.concurrent.ThreadPoolExecutor.runWorker(ThreadPoolExecutor.java:1144)
	java.base/java.util.concurrent.ThreadPoolExecutor$Worker.run(ThreadPoolExecutor.java:642)
	java.base/java.lang.Thread.run(Thread.java:1583)
```
#### Short summary: 

QDox parse error in file://<WORKSPACE>/benchmarks/datasets/Main.java