import java.util.Scanner;

public class FactorialTailRecursive {
    public static long factTail(int n, long acc) {
        if (n <= 1) return acc;
        return factTail(n-1, acc * n);
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int n = scanner.nextInt();
        System.out.println(n + "! = " + factTail(n, 1));
    }
}