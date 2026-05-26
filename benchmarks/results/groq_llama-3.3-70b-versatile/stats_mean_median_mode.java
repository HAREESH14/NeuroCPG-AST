import java.util.Scanner;

public class Stats {
    public static void sort(int[] a, int n) {
        for (int i = 0; i < n-1; ++i)
            for (int j = 0; j < n-i-1; ++j)
                if (a[j] > a[j+1]) { int t=a[j]; a[j]=a[j+1]; a[j+1]=t; }
    }

    public static float mean(int[] a, int n) {
        int s = 0;
        for (int i = 0; i < n; ++i) s += a[i];
        return ((float)s)/n;
    }

    public static float median(int[] a, int n) {
        int[] b = new int[n];
        System.arraycopy(a, 0, b, 0, n);
        sort(b, n);
        if (n % 2 == 1) return b[n/2];
        return (b[n/2 - 1] + b[n/2]) / 2.0f;
    }

    public static int mode(int[] a, int n) {
        int best = a[0], best_count = 1;
        for (int i = 0; i < n; ++i) {
            int cnt = 1;
            for (int j = i+1; j < n; ++j) if (a[j] == a[i]) ++cnt;
            if (cnt > best_count) { best_count = cnt; best = a[i]; }
        }
        return best;
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int n = scanner.nextInt();
        if (n > 100) n = 100;
        int[] data = new int[n];
        for (int i = 0; i < n; i++) data[i] = scanner.nextInt();
        System.out.print("Data: ");
        for (int i=0;i<n;i++) System.out.print(data[i] + " ");
        System.out.println();
        System.out.printf("Mean: %.2f\n", mean(data,n));
        System.out.printf("Median: %.2f\n", median(data,n));
        System.out.printf("Mode: %d\n", mode(data,n));
    }
}